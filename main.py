
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
import json
from time import sleep
# import vlc
from tqdm import tqdm
from selenium.webdriver.chrome.options import Options
import traceback
import os
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient import discovery
import re
from pprint import pprint
import warnings

warnings.filterwarnings("ignore")


###############     FILES NEEDED      ####################

# webdriver_path_file.json -> path to chrome driver
# apartment_data -> folder with apartment data for each area. Non-existing json files are creates.
# login_file = 'bot.json' -> username and password for messenger bot



###############      PARAMETERS       ####################

# path to chrome driver
with open('webdriver_path_file.json', encoding='utf-8') as fp:
    webdriver_path = json.load(fp)

webdriver_path = webdriver_path['webdriver_path']



MAX_PRICE_4rooms = 21000 # implemented in room dependent if statement
MAX_PRICE_5rooms = 30000 # implemented in search url
NUM_PAGES = 3 # Max number of pages to scrape for each area
MIN_RENTAL_PERIOD = 12 # Minimum rental period = 12 months. Options: 6 (1-11 months), 12 (12-23 months), 24 (24+ months) and 0 (unlimited)
TEST_MODE = False # when TRUE we loop over TEST_AREAS with shorter waiting times, when FALSE we loop over AREAS with longer waiting times.

# for each area in CPH we need a specific URL from boligportalen. We want to differentiate apartments by area in the end. Filter by max price
AREAS = {
    'København Ø':      'https://www.boligportal.dk/lejeboliger/k%C3%B8benhavn/4-5-v%C3%A6relser/k%C3%B8benhavn-%C3%B8/?max_monthly_rent={}&min_rental_period={}'.format(MAX_PRICE_5rooms, MIN_RENTAL_PERIOD),
    'København V':      'https://www.boligportal.dk/lejeboliger/k%C3%B8benhavn/4-5-v%C3%A6relser/k%C3%B8benhavn-v/?max_monthly_rent={}&min_rental_period={}'.format(MAX_PRICE_5rooms, MIN_RENTAL_PERIOD),
    'København N':      'https://www.boligportal.dk/lejeboliger/k%C3%B8benhavn/4-5-v%C3%A6relser/k%C3%B8benhavn-n/?max_monthly_rent={}&min_rental_period={}'.format(MAX_PRICE_5rooms, MIN_RENTAL_PERIOD),
    'København K':      'https://www.boligportal.dk/lejeboliger/k%C3%B8benhavn/4-5-v%C3%A6relser/k%C3%B8benhavn-k/?max_monthly_rent={}&min_rental_period={}'.format(MAX_PRICE_5rooms, MIN_RENTAL_PERIOD), 
    'Frederiksberg':    'https://www.boligportal.dk/lejeboliger/k%C3%B8benhavn/4-5-v%C3%A6relser/frederiksberg/?max_monthly_rent={}&min_rental_period={}'.format(MAX_PRICE_5rooms, MIN_RENTAL_PERIOD), 
    'Frederiksberg C':  'https://www.boligportal.dk/lejeboliger/k%C3%B8benhavn/4-5-v%C3%A6relser/frederiksberg-c/?max_monthly_rent={}&min_rental_period={}'.format(MAX_PRICE_5rooms, MIN_RENTAL_PERIOD),
    'Valby':            'https://www.boligportal.dk/lejeboliger/k%C3%B8benhavn/4-5-v%C3%A6relser/valby/?max_monthly_rent={}&min_rental_period={}'.format(MAX_PRICE_5rooms, MIN_RENTAL_PERIOD)
    # Add more areas and corresponding URLs
}

# https://www.boligportal.dk/lejeboliger/k%C3%B8benhavn/4-5-v%C3%A6relser/valby/?max_monthly_rent=21000&min_rental_period=12

# dic of dic of dic. {area -> {url -> {title->title, location->location, price->price}}}. saved in apartments_{area}.json
seen_apartments = {} 

TEST_AREAS = {
    'Valby':            'https://www.boligportal.dk/lejeboliger/k%C3%B8benhavn/4-5-v%C3%A6relser/valby/?max_monthly_rent={}&min_rental_period={}'.format(MAX_PRICE_5rooms, MIN_RENTAL_PERIOD)
}



###############    SCRAPING FUNCTIONS       ####################


def load_seen_apartments(area):
    # Load the seen_apartments for a specific area with correct encoding for Danish alphabet.
    # If file does not already exist or there is an error, we define 'seen_apartments[area]' as empty dic.
    filename = 'apartment_data/apartments_{}.json'.format(area)
    if not os.path.isfile(filename) or os.stat(filename).st_size == 0:
        seen_apartments[area] = {}
    else:
        with open(filename, encoding='utf-8') as fp:
            try:
                seen_apartments[area] = json.load(fp)
            except json.JSONDecodeError:
                seen_apartments[area] = {}
    return None

def scrape_and_soupify(url):

    driver.get(url)
    rendered_source = driver.page_source
    soup = BeautifulSoup(rendered_source, features="html.parser")

    return soup

def get_apartment_data(soup_apartment):

    location = soup_apartment.select_one('.css-1w4wg57').text.strip()
    title = soup_apartment.select_one('.css-qkckqn').text.strip()
    description = soup_apartment.select_one('.css-js2eza').text.strip()
    price = soup_apartment.select_one('.css-1slo7p8 .css-1wff848').text.strip()

    # extract size of apartment
    # string_desc = data['description']
    if ',' in description:
        rooms = str(description)[:8] # 3,5 vær.
        size = re.sub(r'\D', '', str(description))[2:]+' m\u00b2' # 100 m^2
    else:
        rooms = str(description)[:6] # 4 vær.
        size = re.sub(r'\D', '', str(description))[1:]+' m\u00b2' # 4 vær. - 100 m^2

    apartment_area = location.split(',')[0]

    apartment_data = {
        'title': title,
        'rooms' : rooms,
        'size' : size,
        'rooms' : rooms,
        'location': location,
        'price': price
    }

    return apartment_data, apartment_area

def check_if_apartment_is_new(apartment_url):
    seen_urls = seen_apartments.get(area, {}).keys() # To check if apartment is new.

    # check if apartment is new. There are equivalent urls for english and danish versions. We check that neither is already seen.
    if apartment_url.replace("vaer", "room") not in seen_urls and apartment_url.replace("room", "vaer") not in seen_urls:
        return True
    else:
        return False


# use to updates jsons and seen_apartments
def update_with_new_apartment(area, url, apartment_data):
    seen_apartments.setdefault(area, {})[url] = apartment_data


    # dumps new apartments to area specific JSON file.
    with open('apartment_data/apartments_{}.json'.format(area), 'w+', encoding='utf-8') as fp:
        json.dump(seen_apartments.get(area, {}), fp, indent=True, ensure_ascii=True)

    # print('                                   '                     )
    # print('---------  NEW APARTMENT  ---------'                     )                
    # print('                                   '                     )
    # print('Title:           ' + str(apartment_data['title'])        )
    # print('Timestamp:       ' + str(apartment_data['timestamp'])    )
    # print('Size:            ' + str(apartment_data['size'])         )
    # print('Location:        ' + str(apartment_data['location'])     )
    # print('Price:           ' + str(apartment_data['price'])        )
    # print('URL:             ' + str(url)                            )
    # print('                                   '                     )

    return None

# Function to remove apartments from the JSON file that are no longer present
def remove_old_apartments(area, urls_scraped):
    if area in seen_apartments:
        area_apartments = seen_apartments[area]

        # Check each previously seen apartment
        for url in list(area_apartments.keys()):
            if url.replace("vaer", "room") not in urls_scraped and url.replace("room", "vaer") not in urls_scraped:
                # Apartment is no longer present, remove it from JSON file
                del area_apartments[url]

        # Update the JSON file
        with open('apartment_data/apartments_{}.json'.format(area), 'w+', encoding='utf-8') as fp:
            json.dump(area_apartments, fp, indent=True, ensure_ascii=True)

    return None


############# GOOGLE SHEET FUNCTIONS #####################

def open_sheets():

    # Load credentials from the JSON file 
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credentials_filename = 'scraping-of-boligportalen-cb3697df11d6.json'
    credentials = Credentials.from_service_account_file(credentials_filename, scopes=scope)

    # Authenticate with the Google Sheets API
    client = gspread.authorize(credentials)

    # Open the existing spreadsheet
    spreadsheet = client.open('Boligportalen.dk')
    service = discovery.build('sheets', 'v4', credentials=credentials)

    return spreadsheet, service 


def get_sorteret_fra(spreadsheet, service):

    spreadsheet_id = spreadsheet.id
    sorteret_fra_request = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range='Sorteret fra!H:K')
    sorteret_fra_response = sorteret_fra_request.execute()
    values = sorteret_fra_response['values']
    

    return values


def upload_to_sheets(area, service):
    # get the apartment data
    load_seen_apartments(area)

    # get area specific sheet and ID
    sheet = spreadsheet.worksheet(area)
    spreadsheet_id = spreadsheet.id
    

    # save manually inputted data. [Kommentar, skrevet, svar, fremvisning]
    save_request = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range="'{}'!A3:K40".format(area) )
    save_response = save_request.execute()

    # dic with data as keys and manual comments as items.
    data2comment = {tuple(data[7:11]): data[:5] for data in save_response['values']}
    

    # clear current data
    # "'København Ø'!F3:K40"
    clear_request = service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range="'{}'!A3:K40".format(area) , body={})
    clear_response = clear_request.execute()
    


    # Iterate through the data and update the cells
    num = 3  # Starting row index
    for url, data in seen_apartments[area].items():

        # Update the cells with values
        data2upload = ['Link', data['timestamp'], data['rooms']+' - '+data['size'], data['location'], data['price'], data['title']]
        comment2upload = data2comment.setdefault(tuple(data2upload[2:]), ['']*5) # returns comment associated with data or 5 empty values if data is new. 5 as in between column is included

        if data2upload[2:] in sorteret_fra:
            continue
        
        range_for_data = 'A{}:K{}'.format(num, num)
        sheet.update(range_for_data, [comment2upload + data2upload]) # update with date info

        # formula for link to apartment
        hyperlink_formula = '=HYPERLINK("{}";"Link")'.format(url)
        sheet.update_cell(num, 6, hyperlink_formula) # need update_cell for function? YES.

        num += 1
        
    return None



####################    MESSENGER FUNCTIONS     ########################

def open_messenger():

    # username and password saved in json file.
    login_file = 'bot.json'
    with open(login_file, encoding='utf-8') as fp:
        login = json.load(fp)


    # Initialize the Chrome WebDriver
    messenger_driver = webdriver.Chrome(service=Service(webdriver_path))

    messenger_driver.get("https://www.messenger.com")
    messenger_driver.implicitly_wait(15)  # Wait for 10 seconds for the page to load

    # locate elements by their xpath
    xpath_button = "//button[text()='Decline optional cookies']"
    cookies_button = messenger_driver.find_element(By.XPATH, xpath_button)
    cookies_button.click()
    messenger_driver.implicitly_wait(10)  # Wait for 10 seconds for the page to load

    email_input = messenger_driver.find_element(By.XPATH, '//*[@id="email"]')
    email_input.send_keys(login['messenger_user'])

    password_input = messenger_driver.find_element(By.XPATH, '//*[@id="pass"]')
    password_input.send_keys(login['messenger_password'])

    login_button = messenger_driver.find_element(By.XPATH, '//*[@id="loginbutton"]')
    login_button.click()
    messenger_driver.implicitly_wait(90)  # Wait for 60 seconds for the page to load

    chat_button = messenger_driver.find_element(By.XPATH, "//span[contains(text(), 'Gritt, Mette, Asker')]")
    chat_button.click()
    messenger_driver.implicitly_wait(20) 

    return messenger_driver


def send_messenger_text(area, url):

    text = 'Hej med jer, der er en ny lejlighed i {}.'.format(area)+' hej hej.'

    message_input = messenger_driver.find_element(By.CSS_SELECTOR, 'div[contenteditable="true"][aria-label="Message"]')
    message_input.send_keys(text)
    message_input.send_keys(Keys.ENTER)

    message_input.send_keys(url)
    message_input.send_keys(Keys.ENTER)

    return None



####################    MAIN FUNCTION     ########################


# checks ifs, collects above functions and update both jsons and seen_apartments. Sends text message
def from_soup_to_updated_jsons(soup):
    apt_cards = soup_search.find_all('a', {'class': ['AdCardSrp__Link css-17x8ssx']})


    for apt in apt_cards:


        apartment_url = 'https://www.boligportal.dk'+apt['href']

        urls_scraped.append(apartment_url)
        apartment_data, apartment_area = get_apartment_data(apt)
        price_int = int(''.join(filter(str.isdigit, apartment_data['price'])))

        if apartment_area == area: # check 2 : apartment is current area

            # check 3 : rooms and prices
            if ( apartment_data['rooms'] in ['3,5 vær.','4 vær.'] and price_int < MAX_PRICE_4rooms ) or apartment_data['rooms'] in ['4,5 vær.','5 vær.']:

                soup_apartment = scrape_and_soupify(apartment_url)
                timestamp = soup_apartment.select_one('.css-v49nss').text.strip() #last piece of data - timestamp
                apartment_data['timestamp'] = timestamp

                data2upload = [
                        'Link', 
                        apartment_data['timestamp'], 
                        apartment_data['rooms']+' - '+apartment_data['size'], 
                        apartment_data['location'], apartment_data['price'], 
                        apartment_data['title']
                    ]


                if data2upload[2:] not in sorteret_fra: # check 4 : have we discarded it manually?
                        
                    update_with_new_apartment(area, apartment_url, apartment_data)

                    if check_if_apartment_is_new(apartment_url) and messenger_isopen: # check 1 : apartment listing is new and code managed to open messenger

                        send_messenger_text(area, apartment_url)




####################    CODE STARTS HERE    #########################


counter = 0
if __name__ == '__main__':
    while True: 
        try:

            chrome_options = Options()
            chrome_options.add_argument("--headless")

            # opens chrome and goes to boligportalen.dk / search string 
            driver = webdriver.Chrome(service=Service(webdriver_path),options=chrome_options)


            spreadsheet, service = open_sheets()
            sorteret_fra = get_sorteret_fra(spreadsheet, service)


            try:
                messenger_driver = open_messenger()
                messenger_isopen = True
            except:
                print('CANT OPEN MESSENGER')
                messenger_isopen = False


            if TEST_MODE:
                search_areas = TEST_AREAS
                waiting_time_area = 5
                waiting_time_refresh = 10
            else:
                search_areas = AREAS
                waiting_time_area = 30
                if counter == 9:
                    waiting_time_refresh = 15*60
                    counter = 0
                else:
                    waiting_time_refresh = 3*60
                    counter += 1

            for area, AREA_URL in search_areas.items():

                urls_scraped = [] # to keep track of all apartments currently listed (new or not). Allow us to remove old ones afterwards.

                load_seen_apartments(area) 

                print('Fetching apartments in {}...'.format(area))

                
                # Page 1 of search results
                soup_search = scrape_and_soupify(AREA_URL)




                from_soup_to_updated_jsons(soup_search)



                # IN CASE OF MORE PAGES
                # Check if pagination element exists and get the total number of pages (we maximally go through NUM_PAGES pages)
                pagination_element = soup_search.select_one('.Pagination__PageLink.Pagination__PageLink--next')
                if pagination_element is not None:
                    total_pages = min(NUM_PAGES, int(pagination_element.previous_sibling.text))

                    for page in range(1, total_pages + 1):
                        page_url = AREA_URL+'?offset={}'.format(18*page)

                        soup_page = scrape_and_soupify(page_url)
                        from_soup_to_updated_jsons(soup_page)


                remove_old_apartments(area, urls_scraped)



                ############# GOOGLE SHEETS #####################

                upload_to_sheets(area, service)

                for _ in tqdm(range(waiting_time_area), desc='Waiting before scraping next area...'):
                    sleep(1)

                ################################################


            driver.quit()
            # time in between code executions = 10 sec. Change to 60 sec when done.
            for _ in tqdm(range(waiting_time_refresh), desc='Waiting before refresh...'): 
                sleep(1)


        except Exception as err: 
            print('Error:', err)

            traceback.print_exc()  # Print the full traceback

            for _ in tqdm(range(120), desc='Error: trying again in 2 min...'): 
                sleep(1)

            continue
















































