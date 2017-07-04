from bs4 import BeautifulSoup
import urllib.request
import urllib.parse
import threading
import queue
import time
import sys
import os


class E:
    number_of_threads = 6
    number_of_pages = []
    multiple_pages = False
    organize = False

    q = queue.Queue()
    page_q = queue.Queue()
    lock = threading.Lock()

    imgs_downloaded = 0
    total_img_found = 0
    already_found = 0

    content_type_error = []
    HTTP_error = []
    retry_error = []
    value_error = []
    img_error = []
    url_error = []

def main(args):
    if len(args) < 2:
        print("No arguments given")
        print("\n>tty --help (for help and more options)")
        input("\nPress Enter to continue")
        sys.exit()

    # Parses argument flags -- might change with argparse module
    argument_flags(args)
    E.url = format_url(args[1])

    # Parse page urls for images
    if E.multiple_pages:
        E.number_of_pages.sort(key=int)
        for page in E.number_of_pages:
            E.page_q.put(page)
        print("Fetching source for:")
        E.number_of_pages.clear()
        start_threads(4, work_page)
    else:
        print("Fetching page source...")
        html = fetch(E.url)
        page_number = E.url.rsplit("/", 1)[1]
        if not page_number.isdigit():
            page_number = None
        if html is not None:
            parse_page(html, page_number)
        else:
            sys.exit()
    E.total_img_found = E.q.qsize()

    # Starts the download
    lock = threading.Lock()
    print("\nStarting download:")
    start_threads(E.number_of_threads, DL)
 
    # Retry in slow mode if there was any timeout errors
    if len(E.retry_error) > 0:
        print("\n{} image{} were interrupted, retrying in slow mode:".format(len(E.retry_error), "s" if len(E.retry_error) > 1 else ""))
        for x in E.retry_error:
            E.q.put(x)
        start_threads(1, DL)

    # Final report
    print("\nDone!")
    print("Found:", E.total_img_found)
    if E.imgs_downloaded > 0:
        print("Saved:", E.imgs_downloaded)
    if E.already_found > 0:
        print("Already saved:", E.already_found)

    if len(E.HTTP_error) > 0:
        print("\nHTTP error:")
        [print(url) for url in E.HTTP_error]
    if len(E.img_error) > 0:
        print("\nCould not load:")
        [print(url) for url in E.img_error]
    if len(E.url_error) > 0:
        print("\nCould not open:")
        [print(url) for url in E.url_error]

def start_threads(number_of_threads, _target):
    img_threads = [threading.Thread(target=_target, daemon=True)
                   for i in range(int(number_of_threads))]
    for thread in img_threads:
        thread.start()
        time.sleep(0.1)
    for thread in img_threads:
        thread.join()

def DL():
    while E.q.qsize() > 0:
        data = E.q.get()
        url = data["url"]
        date = data["date"]
        page = " -page /{}".format(data["page"]) if data["page"] is not None else ""

        # Corrects the url for some cases
        url = special_case_of_tistory_formatting(url)
        url = format_url(url)

        # Returns image headers in a dictionary, or None if error
        img_info = fetch(url, retry=data["retry"], img_headers=True, page=page) 
        if img_info == None:
            continue
        elif "_TimeoutError_" == img_info:
            data["retry"] = False
            E.retry_error.append(data)
            continue

        # Filter out files under 10kb
        if (img_info["Content-Length"].isdigit() and
            int(img_info["Content-Length"]) < 10000):
            E.total_img_found -= 1
            continue

        # Filter out non jpg/gif/png
        types = ["image/jpeg", "image/png", "image/gif"]
        if img_info["Content-Type"] not in types:
            E.total_img_found -= 1
            continue

        print(url)
        mem_file = fetch(url, retry=data["retry"], page=page)
        if mem_file == None:
            continue
        elif "_TimeoutError_" == mem_file:
            data["retry"] = False
            E.retry_error.append(data)
            continue

        with E.lock:
            img_path = get_img_path(url, date, img_info)
            if img_path != None:
                img_file = open(img_path, "wb")
                img_file.write(mem_file)
                img_file.close()
                E.imgs_downloaded += 1
            else:
                E.already_found += 1

def get_img_path(url, date, img_info):
    s_types = [".jpg", ".jpeg", ".png", ".gif"]
    file_name = img_info["Content-Disposition"]
    if file_name == None:
        file_name = url.split("/")[-1]
        for s_type in s_types:
            if file_name.endswith(s_type):
                file_name = file_name.rsplit(".", 1)[0]
    else:
        if "filename*=UTF-8" in file_name:
            file_name = file_name.split("filename*=UTF-8''")[1]
            file_name = file_name.rsplit(".", 1)[0]
        else:
            file_name = file_name.split('"')[1]
        file_name = urllib.request.url2pathname(file_name)
    extension = "." + img_info["Content-Type"].split("/")[1]
    extension = extension.replace("jpeg", "jpg")
    file_name = file_name + extension
    if E.organize:
        if date == "":
            date = "Untitled"
        no_good_chars = '\/:*?"<>|.'
        folder_name = date 
        for char in no_good_chars:
            folder_name = folder_name.replace(char, "")
        img_path = os.path.join(folder_name.strip(), file_name.strip())
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)
    else:
        img_path = file_name.strip()

    for _ in range(999):
        if not os.path.exists(img_path):
            return img_path
        else:
            if int(img_info["Content-Length"]) != int(len(open(img_path, "rb").read())):
                number = file_name[file_name.rfind("(")+1:file_name.rfind(")")]
                if number.isdigit and file_name[file_name.rfind(")")+1:].lower() in s_types:
                    file_number = int(number) + 1
                    file_name = file_name.rsplit("(", 1)[0].strip()
                else:
                    file_number = 2
                    file_name = file_name.rsplit(".", 1)[0]
                file_name = file_name.strip() + " (" + str(file_number) + ")" + extension
                if E.organize:
                    img_path = os.path.join(folder_name.strip(), file_name.strip())
                else:
                    img_path = file_name.strip()
            else:
                return None

def fetch(url, img_headers=False, retry=False, page=""):
    headers = {
            "User-Agent" : "Mozilla/5.0 (Linux; Android 6.0; Nexus 5" \
            " Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko)" \
            " Chrome/59.0.3071.86 Mobile Safari/537.36",
            }
    try:
        req = urllib.request.Request(url, headers=headers)
        r = urllib.request.urlopen(req)
        if img_headers:
            data = r.info()
        else:
            data = r.read()
        return data 
    except urllib.error.HTTPError as error:
        print(url, error)
        E.HTTP_error.append(url + str(page))
    except urllib.error.URLError as error: # not a valid host url
        print(url, error)
        E.url_error.append(url + str(page))
    except ValueError as error: # missing http/https
        print(url, error)
        E.url_error.append(url + str(page))
    except:
        if retry:
            return "_TimeoutError_"
        else:
            E.img_error.append(url)

def help_message():
    print(
        'usage: tty "url"\n'
        "    Download images from a tistory page\n"
        "    >tty http://idol-grapher.tistory.com/140\n\n"
        "optional:\n"
        "-p, --pages\n"
        "    Download images from multiple pages\n\n"
        "    To download images from page 140 to 150\n"
        "    >tty http://idol-grapher.tistory.com/ -p 140-150\n\n"
        "    To download images from page 1, 2 and 3\n"
        "    >tty http://idol-grapher.tistory.com/ -p 1,2,3\n\n"
        "    To download images from page 1, 2, 3, 5 to 10 and 20 to 25\n"
        "    >tty http://idol-grapher.tistory.com/ -p 1,2,3,5-10,20-25\n\n"
        "-t, --threads\n"
        "    Number of simultaneous downloads (max is 32)\n"
        "    >tty http://idol-grapher.tistory.com/140 -t 6\n\n"
        "-o, --organize\n"
        "    Organize images by title (may not always work)\n"
        "    >tty http://idol-grapher.tistory.com/140 -o")
    sys.exit()

def error_message(error):
    print(error)
    print("\nFor help and more options:")
    print(">tty --help")
    sys.exit()

def format_url(url):
    if url.startswith('"'):
        url = url.strip('"')
    if url.startswith("/"):
        url = "http://" + url.strip("/")
    if url.startswith("http://www."):
        url = "http://" + url[11:]
    elif url.startswith("www."):
        url = "http://" + url[4:]
    return url      # http://idol-grapher.tistory.com/

def special_case_of_tistory_formatting(url):
    if "=" in url and "tistory.com" in url:
        url = urllib.request.url2pathname(url)
        url = url.split("=")[-1]
        return url
    else:
        return url

def split_pages(p_digits):
    digit_check = p_digits.replace(",", " ")
    digit_check = digit_check.replace("-", " ").split(" ")
    for digit in digit_check:
        if not digit.isdigit():
            digit_error = "-p only accept numbers\n" \
                          ">tty http://idol-grapher.tistory.com/ -p 1,2,3-10"
            error_message(digit_error)
    p_digits = p_digits.split(",")
    for digit in p_digits:
        if "-" in digit:
            first_digit = digit.split("-")[0]
            second_digit = digit.split("-")[1]
            if int(second_digit) > int(first_digit):
                total_digit = int(second_digit) - int(first_digit)
            else:
                negative_error = "{}\n" \
                                 "Can't go from '{} to {}'\n" \
                                 ">tty http://idol-grapher.tistory.com/ -p 1-10".format(digit, first_digit, second_digit)
                error_message(negative_error)
            for new_digit in range(total_digit + 1):
                E.number_of_pages.append(new_digit + int(first_digit))
        else:
            E.number_of_pages.append(int(digit))

def argument_flags(args):
    if "-h" in args or "--help" in args:
        help_message()
    if "-p" in args or "--pages" in args:
        E.multiple_pages = True
        try:
            split_pages(args[args.index("-p" if "-p" in args else "--pages") + 1])
        except IndexError:
            page_error = "{} needs an argument\n\n" \
                         "Example:\n" \
                         ">tty http://idol-grapher.tistory.com/ -p 1-5".format("-p" if "-p" in args else "--pages")
            error_message(page_error)
    if "-t" in args or "--threads" in args:
        try:
            thread_num = args[args.index("-t" if "-t" in args else "--threads") + 1]
        except IndexError:
            thread_num_error = "{} needs an argument\n\n" \
                               "Example:\n" \
                               ">tty http://idol-grapher.tistory.com/244 -t 6".format("-t" if "-t" in args else "--threads")
            error_message(thread_num_error)
        if (thread_num.isdigit() and
            int(thread_num) > 0 and
            int(thread_num) < 33):
            E.number_of_threads = int(thread_num)
        else:
            thread_num_error = "-t needs a number in between 1-32\n" \
                               ">tty http://idol-grapher.tistory.com/244 -t 6"
            error_message(thread_num_error)
    if "-o" in args or "--organize" in args:
        E.organize = True
    
def parse_page(html, page_number):
    data = {}
    soup = BeautifulSoup(html, "html.parser")
    try:
        date = soup.find(property="og:title").get("content")
    except AttributeError:
        date = soup.title.string
    for tag in soup.find_all("img"):
        url = tag.get("src")
        if "tistory.com" in url and "image" in url:
            url = url.replace("image", "original")
        if "daumcdn.net" not in url:
            data["date"] = date
            data["url"] = url
            data["page"] = page_number
            data["retry"] = True
            E.q.put(data.copy())

def work_page():
    while E.page_q.qsize() > 0:
        page_number = E.page_q.get()
        url = E.url + str(page_number)
        html = fetch(url)
        if html is not None:
            parse_page(html, page_number)
        else:
            sys.exit()

if __name__ == "__main__":
    main(sys.argv)
