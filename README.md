# SDGB-DOWNLOAD-ORDER
A MaimaiDX CHN Options Download Tools
该Python脚本代码使用 Deepseek R1 & V3 生成
请安装以下第三方库后使用
requests
pycryptodome
tqdm

2.0更新内容（2025/12/24）
将unsega和7zip整合到了tools文件夹
增加了请求头UA验证，增加多线程下载（可自行修改线程数）
删除文件时将不再删除原盘文件，仅删除vhd

如果数字版本出现更新变动后无法获取到新版opt，请在get_download_ur用法中找到payload，并将title_ver修改到最新版本即可
