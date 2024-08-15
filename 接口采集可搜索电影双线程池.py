import requests
import os
import threading
import queue
import logging
import subprocess
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.abspath(os.path.dirname(__file__))
PARENT_DIR = os.path.abspath(os.path.join(HERE, os.path.pardir))

# 设置日志配置
logging.basicConfig(level=logging.INFO, format='[%(thread)d] %(asctime)s - %(levelname)s - %(message)s')


# 用户需要修改的变量
download_path = r'D:\gongxiang\电视剧'
resule_file = "双线程池采集结果.txt"  # 输出文件名
# ffmpeg视频解码 https://github.com/BtbN/FFmpeg-Builds
# https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip
ffmpeg_path = r'D:/java/ffmpeg-master-latest-win64-gpl/bin'
# m3u8跨平台下载器 https://github.com/nilaoda/N_m3u8DL-RE
# https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.2.0-beta/N_m3u8DL-RE_Beta_win-x64_20230628.zip
# 只有单文件 N_m3u8DL-RE.exe
m3u8DL_dir = r'D:/java/ffmpeg-master-latest-win64-gpl/bin'
# 如果没有其他源，请不要变更 BASE_URL
BASE_URL = "https://ikunzyapi.com/api.php/provide/vod/"


# 线程安全的队列和停止标志
task_queue = queue.Queue()
stop_threads = threading.Event()


def execute(args, cwd='/'):
    output = ''
    sp = subprocess.Popen(args, shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          cwd=cwd, bufsize=1)
    stdout = sp.stdout
    while True:
        temp = stdout.readline()
        if temp == '' and sp.poll() is not None:
            break
        else:
            print(temp, end="")
            output = output + temp
    return output

def fetch_category_type():
    """获取分类类型"""
    url = f"{BASE_URL}from/ikm3u8/at/json"
    logging.info("请求分类数据...")
    response = requests.get(url)
    data = response.json()
    types = []
    for c in data['class']:
        type_name = c['type_name']
        type_id = c['type_id']
        types.append((type_id, type_name))
    return types


def fetch_movie_list(type_id, vod_name, page):
    """获取特定类型下的影视列表"""
    url = f"{BASE_URL}?ac=list&t={type_id}&pg={page}"
    if vod_name:
        url = f"{BASE_URL}?ac=list&wd={vod_name}"
    logging.info(f"请求url: {url}")
    if vod_name:
        logging.info(f"请求影视列表: 名称={vod_name}...")
    else:
        logging.info(f"请求影视列表: 类型 ID={type_id}, 页码={page}...")
    response = requests.get(url)
    return response.json()


def fetch_movie_details(movie_ids):
    """获取影视详情"""
    url = f"{BASE_URL}?ac=detail&ids={movie_ids}"
    logging.info(f"请求影视详情: IDs={movie_ids}...")
    response = requests.get(url)
    return response.json()


def parse_play_url(play_url):
    """解析播放 URL"""
    episodes = []
    items = play_url.split('#')

    for item in items:
        if item:
            ep = item.split('$')
            if ep:
                if len(ep) == 2:
                    episodes.append((ep[0], ep[1]))
                else:
                    episodes.append((item, ''))  # 如果没有 URL，保留集数信息
    logging.info(f"解析播放 URL: {episodes}")
    return episodes

def download(mc, urlAttr):
    title, url = urlAttr
    print(mc, title, url)
    mc_path = os.path.join(download_path, mc)
    if not os.path.exists(mc_path):
        os.mkdir(mc_path)
    title_path = os.path.join(mc_path, mc + title + '.mp4')
    if os.path.exists(title_path):
        return
    cmd = f'start {m3u8DL_dir}/N_m3u8DL-RE.exe "{url}" --save-name "{mc}{title}" --save-dir "{mc_path}" --tmp-dir "{mc_path}" --thread-count "16" --download-retry-count "15" --ffmpeg-binary-path "{ffmpeg_path}/ffmpeg.exe" --select-video "best" --auto-select true --no-date-info true --concurrent-download true --use-system-proxy false'
    print('执行的命令：', cmd)
    execute(cmd, m3u8DL_dir)

def process_movie(movie, vod_name):
    """处理单个电影"""
    movie_id = movie['vod_id']
    movie_name = movie['vod_name']
    if stop_threads.is_set():
        logging.info(f" {movie_name} 退出线程")
        return  # 退出当前线程

    if vod_name:
        # 检查 vod_name 是否包含用户指定的名称
        if vod_name in movie_name:
            logging.info(f"找到匹配影视: {movie_name} (ID: {movie_id})")
            movie_details = fetch_movie_details(movie_id)
            for detail in movie_details['list']:
                cover = detail['vod_pic']
                alias = detail['vod_sub']
                play_url = detail['vod_play_url']
                episodes = parse_play_url(play_url)

                # 输出到文件
                with open(os.path.join(download_path, resule_file), 'a', encoding='utf-8') as f:
                    f.write(f"封面: {cover}\n")
                    f.write(f"名称: {movie_name}\n")
                    f.write(f"别名: {alias}\n")
                    f.write("集数和URL:\n")
                    for ep in episodes:
                        f.write(f"  {ep[0]}: {ep[1]}\n")
                    f.write("\n")
                logging.info(f"影视 '{movie_name}' 信息已写入文件.")
            # 找到后设置停止标志
            stop_threads.set()
            logging.info("找到指定电影，正在停止其他线程...")
            return True # 退出当前线程
    else:
        movie_details = fetch_movie_details(movie_id)
        for detail in movie_details['list']:
            cover = detail['vod_pic']
            alias = detail['vod_sub']
            play_url = detail['vod_play_url']
            episodes = parse_play_url(play_url)

            # 输出到文件
            with open(os.path.join(download_path, resule_file), 'a', encoding='utf-8') as f:
                f.write(f"封面: {cover}\n")
                f.write(f"名称: {movie_name}\n")
                f.write(f"别名: {alias}\n")
                f.write("集数和URL:\n")
                for ep in episodes:
                    f.write(f"  {ep[0]}: {ep[1]}\n")
                f.write("\n")
            logging.info(f"影视 '{movie_name}' 信息已写入文件.")
        else:
            return True # 退出当前线程
    return False

def worker(vod_name):
    """工作线程函数"""
    if not stop_threads.is_set():
            if vod_name:
                movie_list_data = fetch_movie_list('', vod_name, '')
                total = movie_list_data['total']
                logging.info(f" {vod_name} 影视获取成功，共 {total} 条")

                # 使用线程池处理每个电影
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = []
                    for movie in movie_list_data['list']:
                        futures.append(executor.submit(process_movie, movie, vod_name))

                    # 等待所有电影处理完成
                    for future in as_completed(futures):
                        if future.result():  # 如果找到匹配的电影
                            return  # 退出当前线程
            else:
                try:
                    type_id, page = task_queue.get(timeout=5)  # 5秒超时

                    movie_list_data = fetch_movie_list(type_id, vod_name, page)
                    total_pages = movie_list_data['pagecount']
                    logging.info(f"第 {page} 页影视列表获取成功，总页数: {total_pages}")

                    # 使用线程池处理每个电影
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        futures = []
                        for movie in movie_list_data['list']:
                            futures.append(executor.submit(process_movie, movie, vod_name))

                        # 等待所有电影处理完成
                        for future in as_completed(futures):
                            if future.result():  # 如果找到匹配的电影
                                return  # 退出当前线程
                except queue.Empty:
                    logging.info("队列为空，等待下一个任务...")
                    return  # 退出当前线程
                except Exception as e:
                    logging.error(f"出现错误: {e}")
                finally:
                    # logging.info(f"第 {page} 页处理完毕")
                    task_queue.task_done()


def download_test():
    with open(os.path.join(download_path, resule_file), 'r', encoding='utf-8') as f:
        lines = f.readlines()

        is_find_url = False
        infos = []
        urls = []
        info = {}
        for line in lines:
            if not line or line == '\n':
                is_find_url = False
                info = {}
                urls = []
            elif is_find_url:
                attrs = line.split(":")
                title = attrs[0].strip()
                url = ":".join(attrs[1:]).strip()
                # print(f'{title}=={url}')
                urls.append((title, url))
            elif line.startswith("封面:"):
                info['fm'] = line[line.index("封面:") + 3:].strip()
            elif line.startswith("名称:"):
                info['mc'] = line[line.index("名称:") + 3:].strip()
            elif line.startswith("别名:"):
                info['bm'] = line[line.index("别名:") + 3:].strip()
            elif line.startswith("集数和URL:"):
                is_find_url = True
                infos.append(info)
                info['urls'] = urls
    for info in infos:
        mc = info['mc']
        urls = info['urls']
        # print(f'{mc}--{urls')

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(download, mc, urlAttr, ) for urlAttr in urls}

            for future in as_completed(futures):
                if future.result():
                    logging.info("下载完毕")


def main():

    types = fetch_category_type()

    for i in range(0, len(types)):
        print(f'{i+1}.{types[i][1]}', end='\t')
    print('')
    type_id = input("请选择分类: ")  # 用户输入要查找的影视名称

    select = types[int(type_id) - 1]
    type_id = select[0]
    type_name = select[1]
    print(f'您选择了： {type_name}')
    print('')

    print(f'直接回车则搜索当前分类全部')
    """主函数"""
    vod_name = input("请输入要查找的影视名称: ")  # 用户输入要查找的影视名称

    # 输出到文件
    with open(os.path.join(download_path, resule_file), 'w+', encoding='utf-8') as f:
        f.write("")
        f.flush()
        f.close()

    max_workers = 5
    if vod_name:
        max_workers = 1

    # 使用线程池进行并发处理
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        if vod_name:
            futures = {executor.submit(worker, vod_name, )}

            for future in as_completed(futures):
                if future.result():
                    logging.info("停止其他线程.")
                    # 取消未完成的任务
                    for f in futures.keys():
                        if f != future:  # 取消其他线程
                            f.cancel()
                    break
        else:

            # 获取分类的总页数
            first_page_data = fetch_movie_list(type_id, 1)
            total_pages = first_page_data['pagecount']
            logging.info(f"总页数: {total_pages}")

            # 将所有页码加入队列
            for page in range(1, total_pages + 1):
                task_queue.put((type_id, page))

            futures = {executor.submit(worker, vod_name, ) for _ in range(1, total_pages + 1)}

            for future in as_completed(futures):
                if future.result():
                    logging.info("找到指定电影，停止其他线程.")
                    # 取消未完成的任务
                    for f in futures.keys():
                        if f != future:  # 取消其他线程
                            f.cancel()
                    break

    # 使用线程池进行并发下载
    print('使用线程池进行并发下载')
    download_test()


if __name__ == "__main__":

    main()