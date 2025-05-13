import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from urllib.parse import unquote
website_prefix = 'https://'
website_root = 'www.saflii.org/za/cases/ZACC/'
url = '{}{}'.format(website_prefix, website_root)
local_folder = 'G:/My Drive/PERSONAL/LEGALPRO/LEGALPRO/DATA/COLLECTION/'
# def scrape_website(url, local_folder):
non_permissible_characters = ["<", ">",":", "'", '"', "/", "\\", "|", "?", "*"] # non permissible for storing on windows file system
y = [1995, 1996, 1997, 1998, 1999, 2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023]
years = [str(yi) for yi in y]
for year in years[:2]:
    
    url_extension = url+year+"/"
    print("url is")
    print(url)
    print("url extension is")
    print(url_extension)
 
    response = requests.get(url_extension)
    soup = BeautifulSoup(response.content, 'html.parser')
# Find all <a> tags with href ending in '.html'
    html_links = soup.find_all('a', href=lambda href: href and href.endswith('.html'))
    for link in html_links:
        url_extension2 = urljoin(url_extension, link['href'])
        print("first url extension in inner loop::  ")
        print(url_extension2)
        try:
            filename = unquote(link.text)
            #print(filename)
    
            for char in filename:
                if char in non_permissible_characters:
                    filename = filename.replace(char, " ")
            #print(filename)
            
            filename_and_path = os.path.join(local_folder, filename)
    
    
            
            # Download the html file
            print('url extensions before download')
            print(url_extension2)
            response = requests.get(url_extension2)
            with open(filename_and_path, 'wb') as f:
                f.write(response.content)
                print(f"Downloaded: {filename_and_path}.html")
        except Exception as e:
            print("ERROR EXCEPTION")
            
            
    # Find all <a> tags with href starting with '/'
    subdirectory_links = soup.find_all('a', href=lambda href: href and href.startswith('/'))
    
    for link in subdirectory_links:
        subdirectory_url = urljoin(url, link['href'])
        scrape_website(subdirectory_url, local_folder)
    


# Set the URL of the website to scrape and local folder to save the html files

# filename = 'H:/My Drive/PERSONAL/LEGALPRO/LEGALPRO/DATA/COLLECTION/{}{}'.format(website_root, filename)

local_folder = 'H:/My Drive/PERSONAL/LEGALPRO/LEGALPRO/DATA/COLLECTION/'

local_folder = 'C:/Users/bseot/Downloads/'

local_folder = 'G:/My Drive/'
#, Call the scrape_website function to start the scraping process
scrape_website(website_url, local_folder)


# soup = BeautifulSoup(response.content, 'html.parser')
# html_links = soup.find_all('a', href=lambda href: href and href.endswith('.html'))
# non_permissible_characters = '<>:"/\|?*' # non permissible for storing on windows file system



# for link in html_links:
#     url = urljoin(url, link['href'])
#     filename = unquote(link.text)
#     for char in filename:
#         if char in non_permissible_characters:
#             filename.replace(char, " ")