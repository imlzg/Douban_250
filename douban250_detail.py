from bs4 import BeautifulSoup
import asyncio
import aiohttp
import datetime
import random
import sys
import json

# function map for achieving specific info in html body
content_func_map = {
    'title': lambda sp: sp.select_one('#content > h1 > span:nth-child(1)').get_text(),
    'year': lambda sp: sp.select_one('#content > h1 > span.year').get_text().replace('(', '').replace(')', ''),
    'director': lambda sp: sp.select_one('#info > span:nth-child(1) > span.attrs > a').get_text(),
    'genre': lambda sp: list(map(lambda item: item.get_text(), sp.select('#info > span[property="v:genre"]'))),
    'score': lambda sp: sp.select_one('#interest_sectl > div.rating_wrap.clearbox > \
                                        div.rating_self.clearfix > strong').get_text()
}
# html parser, maybe 'html', 'lxml', 'html5lib'
html_parser = 'lxml'
# http proxies
proxies = set()
proxies_used = set()
proxy_delay_time = 1
proxy_connection_timeout = 2
# movie urls
movie_urls = []
# task count
task_count = 0
# results
results = []


def get_proxies():
    """
    get proxies from daili.html
    :return:
    """
    for i in range(4):
        html = open('daili/%d.html' % (i + 1), encoding='utf-8').read()
        soup = BeautifulSoup(html, 'lxml')
        for item in soup.select('tr[class="odd"]'):
            ip = item.select_one('td:nth-child(2)').get_text()
            port = item.select_one('td:nth-child(3)').get_text()
            proxies.add('http://%s:%s' % (ip, port))


async def get_random_proxy():
    """
    get a random proxy
    """
    len_proxy = len(proxies)
    while True:
        if len_proxy == 0:
            return ''
        proxy = random.sample(proxies, 1)[0]
        if proxy in proxies_used:
            # limit the speed of one proxy, delay 1s in schedule
            print('代理%s还在使用中，延迟%d秒再找= =' % (proxy, proxy_delay_time))
            await asyncio.sleep(proxy_delay_time)
        else:
            proxies_used.add(proxy)
            return proxy


def get_movie_urls():
    """
    get movie urls
    :return: movie urls
    """
    with open('movie_urls.txt', 'r', encoding='utf-8') as f:
        movie_urls.extend(f.read().splitlines())
        f.close()


async def parse_movie_url(session, url, movie_num):
    """
    fetch html body from url and parse it to get info of movie
    :param session: client session
    :param url: douban movie url
    :param movie_num: the number of movie
    :return: nothing~
    """
    while True:
        proxy = await get_random_proxy()
        if not proxy:
            print('TMD没代理了，凉凉= =')
            return
        # result contains info of a movie
        result = {'number': movie_num, 'url': url, 'proxy': proxy}
        print('电影No.%d的代理%s正在访问%s...' % (movie_num, proxy, url))
        success = False
        try:
            response = await session.get(url, proxy=proxy, timeout=proxy_connection_timeout)
            status_code = response.status
            if status_code == 200:
                html_body = await response.text()
                soup = BeautifulSoup(html_body, html_parser)
                for k in content_func_map.keys():
                    try:
                        content = content_func_map[k](soup)
                        result[k] = content
                    except Exception as e:
                        print('Error on \"%s\" data: %s\n' % (k, e))
            else:
                # maybe 403 forbidden, need to move proxy
                print('代理%s获取电影No.%d数据失败！状态码: %d！' % (proxy, movie_num, status_code))
                if status_code == 403:
                    print('代理%s被403封了，果断放弃掉~')
                    if proxy in proxies:
                        proxies.remove(proxy)
                continue
            # append result
            global results
            results.append(result)
            print('爬到电影信息：%s' % str(result))
            success = True
        except Exception as e:
            # proxy is unavailable
            print('代理%s连接出错，果断放弃掉！！！错误信息：%s！' % (proxy, e))
            if proxy in proxies:
                proxies.remove(proxy)
        finally:
            if proxy in proxies_used:
                proxies_used.remove(proxy)
            if success:
                # end task only if success is true
                # actually need a lock here lol~
                global task_count
                task_count = task_count + 1
                print('爬到信息的电影数: %d' % task_count)
                break


async def main():
    """
    main task
    """
    start_time = datetime.datetime.now()
    # get movie urls
    get_movie_urls()
    # get proxies
    get_proxies()
    print('代理总数: %d\n' % len(proxies))
    if len(proxies) == 0:
        print('没代理了，凉凉= =')
        sys.exit(0)
    # create client session connected to the internet
    async with aiohttp.ClientSession() as session:
        # generate tasks for spider
        tasks = list()
        num_urls = len(movie_urls)
        for i in range(num_urls):
            tasks.append(parse_movie_url(session, movie_urls[i], i + 1))
        # execute tasks
        await asyncio.gather(*tasks)
        # write result to file
        with open('movie_info_async.txt', 'w', encoding='utf-8') as movie_file:
            global results
            results = sorted(results, key=lambda k: k['number'])
            movie_file.write(json.dumps(results, indent=2, ensure_ascii=False))
            movie_file.close()
        # print survived proxies
        print('\n幸存的代理（%d个）：%s\n' % (len(proxies), str(list(proxies))))
        # calculate task time
        time_period = datetime.datetime.now() - start_time
        print('完成时间：%d秒!' % time_period.seconds)


if __name__ == '__main__':
    asyncio.run(main())