import json
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
if not all(getenv(key) for key in ('DOMAIN', 'TOKEN')):
    print("Ошибка: Не все необходимые переменные окружения указаны в файле .env.")
    sys.exit(1)

domainname = getenv('DOMAIN')
token = getenv('TOKEN')
serverurl = f'{domainname}/webservice/rest/server.php'

def get_lecture(lecture_id: int):
    response = requests.get(serverurl, params={
        'wstoken': token,
        'wsfunction': 'core_course_get_course_module',
        'moodlewsrestformat': 'json',
        'cmid': lecture_id,
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

def save_answers(answers):
    with open('answers.json', 'w') as f:
        json.dump(answers, f)

def load_answers():
    try:
        with open('answers.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# Проверяем наличие аргумента с ID лекции
if len(sys.argv) != 2:
    print("Используйте: python main.py <lecture_id>")
    sys.exit(1)

lecture_id = int(sys.argv[1])

# Получаем данные о лекции
lecture = get_lecture(lecture_id)
if 'exception' in lecture:
    print("Ошибка получения лекции с сайта:",lecture['message'])
    sys.exit(1)

if 'cm' in lecture and 'instance' in lecture['cm']:
    lesson_id = lecture['cm']['instance']
    pages = get_lecture_pages(lesson_id)

    if 'pages' in pages and len(pages['pages']) > 0:
        existing_answers = load_answers()
        for page in pages['pages']:
            page_id = page['page']['id']

            page_details = get_lesson_page(lesson_id, page_id)
            qtype = page_details['page']['qtype']
            if qtype not in (3, 8):
                continue

            soup = BeautifulSoup(page_details['page']['contents'], 'html.parser')
            question = soup.find('div', class_='no-overflow').text.strip()
            print("Вопрос:", question)
            question_hash = hashlib.sha256(question.encode()).hexdigest()

            if question_hash in existing_answers:
                print("Ответ уже существует:", existing_answers[question_hash])
                continue

            if qtype == 3:
                soup = BeautifulSoup(page_details['pagecontent'], 'html.parser')
                answer_options = soup.find_all('div', class_='answeroption')

                answers = []
                for idx, option in enumerate(answer_options):
                    answer_text = option.find('span', class_='filter_mathjaxloader_equation').text.strip()
                    print(f"{idx + 1}. {answer_text}")
                    answers.append(answer_text)

                chosen_index = int(input("Выберите номер ответа: "))
                chosen_answer = answers[chosen_index - 1]
            else:
                chosen_answer = input("Введите ответ: ")

            existing_answers[question_hash] = chosen_answer

        save_answers(existing_answers)
    else:
        print("Ошибка: Нет страниц в уроке.")
else:
    print("Ошибка: 'instance' не найден в деталях лекции.")
