import re
import requests
from random import choice
from bs4 import BeautifulSoup
from tldextract import extract
from urllib.parse import urlparse
from requests_ntlm import HttpNtlmAuth
from taser.resources.user_agents import USERAGENTS
from urllib3 import disable_warnings, exceptions
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
disable_warnings(exceptions.InsecureRequestWarning)

class WebSession():
    def __init__(self, headers={}, keep_alive=True):
        self.session = requests.Session()
        self.session.headers.update(headers)

        if 'User-Agent' not in headers:
            self.session.headers.update({'User-Agent': random_agent()})

        if not keep_alive:
            self.session.headers.update({'Connection': 'Close'})

    def retry_request(self, url, method, randomize_agent, headers, timeout, proxies, redirects, max_retries, debug, **kwargs):
        retry = 0
        while retry <= max_retries:
            retry += 1
            x = self.web_request(url, method, randomize_agent, headers, timeout, proxies, redirects, max_retries=0, debug=debug, **kwargs)
            if x:
                return x
        return False

    def web_request(self, url, method='GET', randomize_agent=True, headers={}, timeout=4, proxies=[], redirects=True, max_retries=0, debug=False, **kwargs):
        self.session.headers.update(headers)
        if randomize_agent:
            self.session.headers.update({'User-Agent': random_agent()})

        try:
            req = requests.Request(method, url, headers=self.session.headers, **kwargs)
            prep = req.prepare()
            return self.session.send(prep, timeout=timeout, verify=False, allow_redirects=redirects, proxies=proxy_randomizer(proxies))
        except requests.exceptions.ConnectionError:
            if max_retries > 0:
                return self.retry_request(url, method, randomize_agent, headers, timeout, proxies, redirects, max_retries, debug, **kwargs)
        except requests.exceptions.Timeout:
            if max_retries > 0:
                return self.retry_request(url, method, randomize_agent, headers, timeout, proxies, redirects, max_retries, debug, **kwargs)
        except Exception as e:
            if debug:
                print("Taser:web_request::{}".format(str(e)))
        return False

    def reset_headers(self, headers={}):
        self.session.headers.clear()
        self.session.headers.update(headers)

    def remove_header(self, value):
        self.session.headers.pop(value)

    def close(self):
        self.session.close()


#################################
# Single Web Requests
#################################
def retry_request(url, method, headers, timeout, proxies, redirects, max_retries, debug, **kwargs):
    '''Retry web requests on failure, goes outside requests retry adapter to support proxy rotation'''
    retry = 0
    while retry < max_retries:
        retry += 1
        if debug: print('Retrying web request [{}] - {}'.format(retry, url))
        x = web_request(url, method, headers, timeout, proxies, redirects, max_retries=0, debug=debug, **kwargs)
        if x:
            return x
    return False

def web_request(url, method='GET', headers={}, timeout=4, proxies=[], redirects=True, max_retries=0, debug=False, **kwargs):
    if 'User-Agent' not in headers:
        headers['User-Agent'] = random_agent()

    ses = requests.Session()
    try:
        req = requests.Request(method, url, headers=headers, **kwargs)
        prep = req.prepare()
        return ses.send(prep, timeout=timeout, verify=False, allow_redirects=redirects, proxies=proxy_randomizer(proxies))
    except requests.exceptions.ConnectionError:
        if max_retries > 0:
            return retry_request(url, method, headers, timeout, proxies, redirects, max_retries, debug, **kwargs)
    except requests.exceptions.Timeout:
        if max_retries > 0:
            return retry_request(url, method, headers, timeout, proxies, redirects, max_retries, debug, **kwargs)
    except Exception as e:
        if debug:
            print("Taser.http:web_request::{}".format(str(e)))
    finally:
        ses.close()
    return False

def download_file(source, output):
    f = open(output, 'wb+')
    f.write(web_request(source, timeout=5).content)
    f.close()

def exec_rawRequest(raw_data, scheme='https://', debug=False):
    '''Takes in a raw HTTP request formatted as a string,
    converts into web_request format, and returns the response (dev)'''
    try:
        req = parse_rawRequest(raw_data, scheme)
    except Exception as e:
        if debug: print('Error parsing raw request: {}'.format(str(e)))
        return False
    return web_request(req['url'], method=req['method'], headers=req['headers'], data=req['data'])

def parse_rawRequest(raw_data, scheme):
    tmp = {'headers':{}, 'data':''''''}
    lines = raw_data.splitlines()
    tmp['method'],tmp['page'],tmp['version'] = lines[0].strip().split(' ')
    for line in lines[1:]:
        if line:
            head, val = line.strip().split(': ')
            tmp['headers'][head] = val

            if head == 'Host':
                tmp['url'] = scheme + rm_slash(val) + tmp['page']
        else:
            # Everything after first blank line will be considered data
            for x in range(lines.index(line), lines.index(lines[-1])+1):
                if lines[x]:
                    tmp['data'] += lines[x]
            return tmp
    return tmp


#################################
# HTTP request support functions
#################################
def random_agent():
    return choice(USERAGENTS)

def proxy_randomizer(proxies):
    if proxies:
        tmp = choice(proxies)
        return {"http": tmp,
                "https": tmp}
    return {}

def auth_handler(username, password, auth_type='basic'):
    AUTH = {'basic' :HTTPBasicAuth(username, password),
            'ntlm' : HttpNtlmAuth(username, password),
            'digest': HTTPDigestAuth(username, password),
           }
    return AUTH[auth_type]


#################################
# Request parsing / Data Filtering
#################################
def get_statuscode(resp):
    try:
        return resp.status_code
    except:
        return 0

def get_pagetitle(resp):
    try:
        soup = BeautifulSoup(resp.content, 'lxml')
        return(str(soup.title.string.split(",")[0]).strip().strip('\n'))
    except:
        return "N/A"

def extract_header(header_field, resp):
    try:
        return resp.headers[header_field].strip()
    except:
        return "N/A"

def extract_links(resp, mailto=False, source={'a':'href', 'script':'src', 'link':'href'}):
    links = []
    soup = BeautifulSoup(resp.content, 'lxml')
    for tag in source.keys():
        for link in soup.findAll(tag):
            link = str(link.get(source[tag]))
            if link.startswith("/"):
                links.append(rm_slash(resp.url) + link)
            elif mailto and link.startswith('mailto:'):
                links.append(link)
            elif "://" in link:
                links.append(link)
            else:
                links.append(resp.url+link)
    return list(set(links))

#################################
# URL Parsing / Manipulation
#################################
def extract_webdomain(url):
    x = extract(url)
    if x.suffix:
        return x.domain+'.'+x.suffix
    return x.domain

def extract_subdomain(url):
    return urlparse(url).netloc

def extract_baseURL(url):
    x = urlparse(url)
    return x.scheme+"://"+x.netloc

def ipcheck(data):
    # Check if string contains an IP address
    ip_check = '''(25[0-5]|2[0-4][0-9]|[0-1]?[0-9][0-9]?)\.( 
                25[0-5]|2[0-4][0-9]|[0-1]?[0-9][0-9]?)\.( 
                25[0-5]|2[0-4][0-9]|[0-1]?[0-9][0-9]?)\.( 
                25[0-5]|2[0-4][0-9]|[0-1]?[0-9][0-9]?)'''
    if re.search(ip_check, data):
        return True
    return False

def internal_ipcheck(data):
    # Must submit exact IP not string to check
    ip_check = r'''(^127\.)|(^192\.168\.)|(^10\.)|(^172\.1[6-9]\.)|(^172\.2[0-9]\.)|(^172\.3[0-1]\.)|(^::1$)|(^[fF][cCdD])/'''
    if re.search(ip_check, data):
        return True
    return False

def extract_path(url):
    p = urlparse(url).path
    if not p:
        p = '/'
    return p

def rm_slash(url):
    '''
    Will check if URL has ending "/" and remove. used
    as a support function for extract_links.
    '''
    if url.endswith('/'):
        url = url[:-1]
    return url

def url_format(url):
    '''
    Take in URL and determine if endpoint is a file
    or directory. Returns value with appropriate "/" ending.
    Primarily used in directory brute scripts.
    '''
    u = urlparse(url)
    if any(["." in u.path.split('/')[-1], url.endswith('/'), u.params, u.query]):
        return url
    return url + "/"

def target2url(value, protocol='https'):
    '''
    Take input IP or domain value and return formatted URL
    '''
    if not value.lower().startswith(('http://', 'https://')):
        value = protocol + '://' + value
    return url_format(value)
