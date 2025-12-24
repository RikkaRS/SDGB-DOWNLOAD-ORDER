import re
import os
import shutil
import time
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import math

SEVEN_ZIP_DIR = os.path.join(".tools", "7z")
SEVEN_ZIP_EXE = "7z.exe"
EXFAT_DLL = "Formats/ExFat7z.64.dll"
UNSEGA_EXE = os.path.join(".tools", "unsega.exe")
AES_KEY = bytes([47, 63, 106, 111, 43, 34, 76, 38, 92, 67, 114, 57, 40, 61, 107, 71])
AES_IV = bytes(16)
MAX_WORKERS = 8  # 最大线程数
CHUNK_SIZE = 1024 * 1024 * 2  # 每个分块2MB

def encrypt(data: bytes) -> bytes:
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return cipher.encrypt(pad(data, AES.block_size))

def decrypt(data: bytes, iv: bytes) -> bytes:
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(data), AES.block_size)

def get_download_url() -> str:
    import urllib3
    http = urllib3.PoolManager()
    payload = bytes(16) + b'title_id=SDGB&title_ver=1.52&client_id=A63E01C2805&token=205648745'
    encrypted_data = encrypt(payload)
    response = http.request('POST',
        'http://at.sys-allnet.cn/net/delivery/instruction',
        body=encrypted_data,
        headers={'User-Agent': 'SDGB;Windows/Lite', 'Pragma': 'DFI'}
    )
    decrypted_data = decrypt(response.data[16:], response.data[:16])
    response_text = decrypted_data.decode('utf-8').strip()
    if '|' in response_text:
        return response_text.split('|', 1)[1].strip()
    elif 'uri=' in response_text:
        return response_text.split('uri=', 1)[1].strip()
    return response_text

def extract_file_list(url: str):
    session = requests.Session()
    session.headers.update({"User-Agent": "A63E01C2805"})
    response = session.get(url)
    response.raise_for_status()
    pattern = r'INSTALL\d+=\s*(https?://\S+)'
    urls = re.findall(pattern, response.text)
    filenames = [os.path.basename(url) for url in urls]
    return filenames, urls

def download_chunk(session: requests.Session, url: str, start: int, end: int,
                   temp_file: str, chunk_index: int, progress_bar: tqdm) -> bool:
    headers = {"User-Agent": "A63E01C2805", "Range": f"bytes={start}-{end}"}
    max_retries = 3
    retry_count = 0
    while retry_count < max_retries:
        try:
            response = session.get(url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            with open(temp_file, 'r+b') as f:
                f.seek(start)
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress_bar.update(len(chunk))
            return True
        except Exception as e:
            retry_count += 1
            if retry_count == max_retries:
                print(f"\n分块 {chunk_index} 下载失败: {e}")
                return False
            time.sleep(1)
    return False

def download_file_multithread(url: str, filename: str) -> bool:
    session = requests.Session()
    session.headers.update({"User-Agent": "A63E01C2805"})
    try:
        response = session.head(url, timeout=10)
        response.raise_for_status()
        if 'Content-Length' not in response.headers:
            print("服务器未返回文件大小，使用单线程下载")
            return download_file_single(url, filename)
        total_size = int(response.headers.get('Content-Length', 0))
        if total_size == 0:
            print("文件大小为0，下载失败")
            return False
        print(f"文件总大小: {total_size // (1024 * 1024)}MB")
        print(f"使用 {MAX_WORKERS} 个线程进行下载...")
        temp_filename = filename + ".tmp"
        with open(temp_filename, 'wb') as f:
            f.truncate(total_size)
        chunk_count = MAX_WORKERS
        chunk_size = math.ceil(total_size / chunk_count)
        chunks = []
        for i in range(chunk_count):
            start = i * chunk_size
            end = min(start + chunk_size - 1, total_size - 1)
            if start < total_size:
                chunks.append((i, start, end))
        progress_bar = tqdm(total=total_size, unit='B',
                            unit_scale=True, desc=filename,
                            unit_divisor=1024)
        start_time = time.time()
        completed = 0
        failed_chunks = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_chunk = {}
            for chunk_index, start, end in chunks:
                future = executor.submit(
                    download_chunk, session, url, start, end,
                    temp_filename, chunk_index, progress_bar
                )
                future_to_chunk[future] = (chunk_index, start, end)
            for future in as_completed(future_to_chunk):
                chunk_index, start, end = future_to_chunk[future]
                try:
                    success = future.result()
                    if success:
                        completed += 1
                        elapsed = time.time() - start_time
                        if elapsed > 0:
                            downloaded = progress_bar.n
                            speed = (downloaded / 1024) / elapsed
                            progress_bar.set_postfix(
                                speed=f"{speed:.2f}KB/s",
                                chunks=f"{completed}/{len(chunks)}"
                            )
                    else:
                        failed_chunks.append((chunk_index, start, end))
                except Exception as e:
                    failed_chunks.append((chunk_index, start, end))
                    print(f"\n分块 {chunk_index} 异常: {e}")
        progress_bar.close()
        if failed_chunks:
            print(f"\n有 {len(failed_chunks)} 个分块下载失败，尝试重新下载...")
            for chunk_index, start, end in failed_chunks:
                print(f"重新下载分块 {chunk_index}...")
                success = download_chunk(session, url, start, end,
                                         temp_filename, chunk_index, progress_bar)
                if not success:
                    print(f"分块 {chunk_index} 重试失败")
                    os.remove(temp_filename)
                    return False
        if os.path.exists(filename):
            os.remove(filename)
        os.rename(temp_filename, filename)
        elapsed = time.time() - start_time
        avg_speed = (total_size / 1024) / elapsed if elapsed > 0 else 0
        print(f"\n{filename} 下载完成！")
        print(f"大小: {total_size // (1024 * 1024)}MB")
        print(f"用时: {elapsed:.2f}秒")
        print(f"平均速度: {avg_speed:.2f}KB/s")
        return True
    except Exception as e:
        print(f"\n多线程下载失败: {e}")
        print("尝试使用单线程下载...")
        return download_file_single(url, filename)

def download_file_single(url: str, filename: str) -> bool:
    session = requests.Session()
    session.headers.update({"User-Agent": "A63E01C2805"})
    try:
        response = session.get(url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        with open(filename, 'wb') as f:
            progress_bar = tqdm(total=total_size, unit='B',
                                unit_scale=True, desc=filename,
                                unit_divisor=1024)
            start_time = time.time()
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    progress_bar.update(len(chunk))
                    elapsed = time.time() - start_time
                    if elapsed > 0:
                        speed = (progress_bar.n / 1024) / elapsed
                        progress_bar.set_postfix(speed=f"{speed:.2f}KB/s")
            progress_bar.close()
        print(f"\n{filename} 下载完成！大小: {total_size // 1024}KB")
        return True
    except Exception as e:
        print(f"\n单线程下载也失败: {e}")
        return False

def process_with_unsega(opt_filename: str) -> str:
    os.system(f'{UNSEGA_EXE} "{opt_filename}"')
    vhd_filename = os.path.splitext(opt_filename)[0] + ".vhd"
    for _ in range(10):
        if os.path.exists(vhd_filename):
            return vhd_filename
        time.sleep(1)
        print(".", end="", flush=True)
    raise FileNotFoundError(f"未检测到文件 {vhd_filename}")

def extract_vhd_with_7zip(vhd_filename: str) -> str:
    extract_dir = os.path.splitext(vhd_filename)[0]
    os.makedirs(extract_dir, exist_ok=True)
    current_dir = os.getcwd()
    os.chdir(SEVEN_ZIP_DIR)
    vhd_full_path = os.path.join(current_dir, vhd_filename)
    extract_full_dir = os.path.join(current_dir, extract_dir)
    command = f'{SEVEN_ZIP_EXE} x "{vhd_full_path}" -o"{extract_full_dir}"'
    result = os.system(command)
    os.chdir(current_dir)
    if result != 0:
        raise RuntimeError(f"7-Zip 命令返回错误代码: {result}")
    if not os.path.exists(extract_dir) or not os.listdir(extract_dir):
        raise RuntimeError("解压目录为空，解压可能未成功")
    print(f"成功解压到: {extract_dir}")
    return extract_dir

def rename_extracted_folder(extract_dir: str) -> str:
    folder_name = os.path.basename(extract_dir)
    pattern = r'^SDGB_(A\d{3})_\d+_\d$'
    match = re.match(pattern, folder_name)
    if match:
        new_name = match.group(1)
        new_path = os.path.join(os.path.dirname(extract_dir), new_name)
        if os.path.exists(new_path):
            shutil.rmtree(new_path)
        os.rename(extract_dir, new_path)
        print(f"文件夹重命名为: {new_name}")
        return new_path
    print(f"保留原文件夹名: {folder_name}")
    return extract_dir

def cleanup_files(filenames):
    for filename in filenames:
        try:
            if os.path.exists(filename):
                os.remove(filename)
                print(f"已删除: {filename}")
        except Exception as e:
            print(f"删除文件时出错 {filename}: {e}")

def display_file_list(files):
    print("=========SDGB可用OPT下载列表=========")
    for i, name in enumerate(files, 1):
        print(f"{i:2d}. {name}")
    if files:
        print(f"\n当前最新版本: {files[0]}")

def get_user_choice(files_count):
    while True:
        try:
            choice = input("\n请输入要下载的文件序号 (输入0退出): ")
            if choice == '0':
                return None
            choice_int = int(choice)
            if 1 <= choice_int <= files_count:
                return choice_int - 1
            print(f"请输入1-{files_count}之间的数字")
        except ValueError:
            print("请输入有效的数字")

def main():
    print("\n======== SDGB DOWNLOADORDER MADE BY R1KKASAMA ========")
    print("======== THE CODE IS GENERATED BY DEEPSEEK V3 ========")
    try:
        print("开始获取下载页面地址...")
        download_page_url = get_download_url()
        print(f"已获取到下载页面地址: {download_page_url}")
        print("开始解析可下载文件列表...")
        files, urls = extract_file_list(download_page_url)
        if not files:
            print("未找到可下载文件")
            return
        display_file_list(files)
        choice = get_user_choice(len(files))
        if choice is None:
            print("程序退出")
            return
        filename, url = files[choice], urls[choice]
        print(f"\n开始下载: {filename}")
        if not download_file_multithread(url, filename):
            print("下载失败")
            return
        vhd_filename = process_with_unsega(filename)
        extract_dir = extract_vhd_with_7zip(vhd_filename)
        cleanup_files([vhd_filename])
        final_dir = rename_extracted_folder(extract_dir)
        print(f"下载完成！文件保存在: {final_dir}")
    except KeyboardInterrupt:
        print("\n\n用户中断操作")
    except Exception as e:
        print(f"\n程序运行出错: {e}")

if __name__ == "__main__":
    main()

# 代码由Deepseek R1 & V3生成