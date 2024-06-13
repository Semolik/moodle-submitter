import json
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from os import getenv, path
import sys
import hashlib

load_dotenv()

# Проверяем наличие файла .env
if not path.exists('.env'):
    print("Ошибка: Файл .env не найден.")
    sys.exit(1)

# Проверяем наличие необходимых переменных в .env
if not all(getenv(key) for key in ('DOMAIN', 'USERNAME', 'PASSWORD')):
    print("Ошибка: Не все необходимые переменные окружения указаны в файле .env. (DOMAIN, USERNAME, PASSWORD, TOKEN)")
    sys.exit(1)

if len(sys.argv)!=2:
    print("usage: python main.py <lecture_id>")
    sys.exit(1)

def get_site_info():
    response = requests.get(serverurl, params={
        'wstoken': token,
        'wsfunction': 'core_webservice_get_site_info',
        'moodlewsrestformat': 'json',
    })
    return response.json()

domainname = getenv('DOMAIN')
token = getenv('TOKEN')
username = getenv('USERNAME')
password = getenv('PASSWORD')

serverurl = f'{domainname}/webservice/rest/server.php'
login_url = f'{domainname}/login/index.php'

session = requests.Session()
print("Получение токена входа...")
login_page = session.get(login_url)
login_soup = BeautifulSoup(login_page.content, 'html.parser')
hidden_inputs = login_soup.find_all("input", type="hidden")
form_data = {input.get('name'): input.get('value') for input in hidden_inputs}
form_data['username'] = username
form_data['password'] = password
print("Вход в аккаунт...")
response = session.post(login_url, data=form_data)

site_info = get_site_info()

user_id = site_info['userid']

def get_lecture(lecture_id: int):
    response = requests.get(serverurl, params={
        'wstoken': token,
        'wsfunction': 'core_course_get_course_module',
        'moodlewsrestformat': 'json',
        'cmid': lecture_id,
    })
    return response.json()

def get_current_grade(course_id: int, lecture_id: int):
    response = requests.get(serverurl, params={
        'wstoken': token,
        'wsfunction': 'gradereport_user_get_grades_table',
        'moodlewsrestformat': 'json',
        'courseid': course_id,
        'userid': user_id
    })
    grade_data = response.json()
  
    if 'tables' in grade_data and len(grade_data['tables']) > 0:
        for table in grade_data['tables']:
            for item in table['tabledata']:
                if 'itemname' in item and f'id={lecture_id}' in item['itemname']['content']:
                    return float(item['grade']['content'].replace(',', '.'))
    return None

def get_lecture_data(lesson_id: int):
    response = requests.get(serverurl, params={
        'wstoken': token,
        'wsfunction': 'mod_lesson_get_lesson',
        'moodlewsrestformat': 'json',
        'lessonid': lesson_id,
    })
    return response.json()

def get_lecture_pages(lesson_id: int):
    response = requests.get(serverurl, params={
        'wstoken': token,
        'wsfunction': 'mod_lesson_get_pages',
        'moodlewsrestformat': 'json',
        'lessonid': lesson_id,
    })
    return response.json()

def get_lesson_page(lesson_id: int, page_id: int):
    response = requests.get(serverurl, params={
        'wstoken': token,
        'wsfunction': 'mod_lesson_get_page_data',
        'moodlewsrestformat': 'json',
        'pageid': page_id,
        'lessonid': lesson_id,
        'returncontents': 1
    })
    return response.json()


def send_answer(lecture_id: int, page_id: int, sesskey: str, answer: str=None, answerids: list[int]=None, multiple: bool=False):
    print("Отправка ответа...")
    if not answer and not answerids:
        raise Exception('No answer or answerids provided')
    data = {
        'id': lecture_id,
        'pageid': page_id,
        'sesskey': sesskey,
    }
    if answerids:
        if multiple:
            for id_ in answerids:
                data[id_] = 1
            data['_qf__lesson_display_answer_form_multichoice_multianswer']=1
        else:
            data['answerid']=answerids[0]
            data['_qf__lesson_display_answer_form_multichoice_singleanswer']=1
    else:
        data['answer']=answer
        data['_qf__lesson_display_answer_form_shortanswer']=1
    response = session.post(f"{domainname}/mod/lesson/continue.php",data=data)
    return response.text

def save_answers(answers):
    with open('answers.json', 'w') as f:
        json.dump(answers, f)

def load_answers():
    try:
        with open('answers.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def get_answer_options(soup) -> tuple[bool, list[tuple[int, str]]]:
    answer_options = soup.find_all('div', class_='answeroption')
    is_multiple = bool(answer_options[0].find('input',{'class':'form-check-input', 'type': 'checkbox'})) if answer_options else False
    answers = []
    for option in answer_options:
        if is_multiple:
            answer_container = option.find('div', class_='form-check')
            input_tag = answer_container.find('input', class_='form-check-input')
            answer_id = input_tag['name']
            answer_text_tag = answer_container.find('span')
            answer_text = answer_text_tag.get_text(strip=True)
            answers.append((answer_id, answer_text))
        else: 
            input_tag = option.find('input', class_='form-check-input')
            answer_id = int(input_tag['value'])
            label_tag = option.find('label', class_='form-check-label')
            answer_text = label_tag.get_text(strip=True)
            answers.append((answer_id, answer_text))
    return is_multiple, answers

def answer_is_correct(answer_page: str):
    soup = BeautifulSoup(answer_page, 'html.parser')
    result = soup.find_all('div', class_='response')
    if result:
        text = '\n'.join(i.text.strip() for i in result)
        print(text)
        if 'неправильный ответ' not in text:
            return True
    else:
        result = soup.find('div', class_='text_to_html')
        if result:
            print(result.text.strip())
        return True

lecture_id = int(sys.argv[1])

lecture = get_lecture(lecture_id)
if 'exception' in lecture:
    print("Ошибка получения лекции с сайта:",lecture['message'])
    sys.exit(1)

if 'cm' in lecture and 'instance' in lecture['cm']:
    lesson_id = lecture['cm']['instance']
    lesson = get_lecture_data(lesson_id=lesson_id)
    print(lesson['lesson']['name'])
    course_id = lesson['lesson']['course']
    current_grade = get_current_grade(course_id=course_id, lecture_id=lecture_id)
    print("Текущаяя оценка за лекцию:", current_grade, "\n")
    pages = get_lecture_pages(lesson_id)
    query_url = f"{domainname}/mod/lesson/view.php?id={lecture_id}&pageid={pages['pages'][0]['page']['id']}&startlastseen=no"
    response = session.get(query_url, allow_redirects=False)
    soup = BeautifulSoup(response.text, 'html.parser')
    sesskey_input = soup.find('input', {'name': 'sesskey'})
    sesskey = sesskey_input.get('value')
    page_count = len(pages['pages'])
    if 'pages' in pages and page_count > 0:
        existing_answers = load_answers()
        answers_count = 0
        
        for page in pages['pages']:
            page_id = page['page']['id']
            page_details = get_lesson_page(lesson_id, page_id)
            qtype = page_details['page']['qtype']
            if qtype not in (3, 8):
                response = session.post(f"{domainname}/mod/lesson/view.php",data={
                    'id': lecture_id,
                    'pageid': page_id,
                    'sesskey': sesskey,
                    'jumpto': -1
                })
                continue
            soup = BeautifulSoup(page_details['page']['contents'], 'html.parser')
            soup_pagecontent = BeautifulSoup(page_details['pagecontent'], 'html.parser')
            question = soup.find('div', class_='no-overflow').text.strip()
            print("Вопрос:", question)
            question_hash = hashlib.sha256(question.encode()).hexdigest()
            
            if question_hash in existing_answers:
                if qtype==3:
                    multiple, answers = get_answer_options(soup_pagecontent)
                    saved_answers = existing_answers[question_hash]['answers']
                    correct_answers = list(filter(lambda option: option[1] in saved_answers if multiple else option[0] in saved_answers, answers))
                    print("Ответ уже существует:", ','.join([answer[1] for answer in correct_answers]) if multiple else correct_answers[0][1])
                    result = send_answer(
                        lecture_id=lecture_id,
                        page_id=page_id,
                        sesskey=sesskey,
                        answerids=existing_answers[question_hash]['answers'],
                        multiple=existing_answers[question_hash]['multiple']
                    )
                else:
                    print("Ответ уже существует:", existing_answers[question_hash])
                    result = send_answer(lecture_id=lecture_id, page_id=page_id, sesskey=sesskey, answer=existing_answers[question_hash]['answers'][0])
                answer_is_correct(result)
                if page_id==pages['pages'][page_count-1]['page']['id']:
                    response = session.post(f"{domainname}/mod/lesson/view.php",data={
                        'id': lecture_id,
                        'pageid':  -9,
                        'sesskey': sesskey,
                        'jumpto': -1
                    })
                print()
                continue
            if qtype == 3:
                answer_options = soup_pagecontent.find_all('div', class_='answeroption')
                multiple, answers = get_answer_options(soup_pagecontent)
                for idx, option in enumerate(answers):
                    print(f"{idx + 1}. {option[1]}")
                chosen_answers = []
                while True:
                    text = input(f"Выберите номер{'a' if multiple else ''} ответ{'ов через запятую' if multiple else 'а'}: ")
                    numbers = text.split(',') if multiple else [text]
                    for number in numbers:
                        if not number.isdigit():
                            print(f"Некорректный ввод.{' ('+number+')'}")
                            continue
                        chosen_index = int(number)
                        if chosen_index<1 or chosen_index>len(answers):
                            print(f"Некорректный ввод.{' ('+number+')'}")
                            continue
                        chosen_answers.append(answers[chosen_index - 1][0] if multiple else int(answers[chosen_index - 1][0]))
                    break
                result = send_answer(lecture_id=lecture_id, page_id=page_id, sesskey=sesskey, answerids=chosen_answers, multiple=multiple)
            else:
                chosen_answer = input("Введите ответ: ")
                result = send_answer(lecture_id=lecture_id, page_id=page_id, sesskey=sesskey, answer=chosen_answer)
                chosen_answers.append(chosen_answer)
            if answer_is_correct(result):
                existing_answers[question_hash] = {'multiple': multiple, 'answers': chosen_answers}
            else:
                print("Ваш ответ не будет сохранен")
            print()
        save_answers(existing_answers)
        new_grade = get_current_grade(course_id=course_id, lecture_id=lecture_id)
        if new_grade!=current_grade:
            print("Оценка после выполнения скрипта:", new_grade)
            print("Разница в оценках:", round(new_grade-current_grade, 2))
    else:
        print("Ошибка: Нет страниц в уроке.")
else:
    print("Ошибка: 'instance' не найден в деталях лекции.")
