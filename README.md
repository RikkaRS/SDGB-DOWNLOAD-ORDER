# SDGB-DOWNLOAD-ORDER

A MaimaiDX CHN Options Download Tools

该Python脚本代码使用 Deepseek R1 & V3 生成

请安装以下第三方库后使用

requests

pycryptodome

tqdm

完全自动化的SDGB Options获取工具！从服务器获取配信文本，截取文本当中的下载链接和文件名提供可选下载选项，通过多线程的方式进行下载，下载完成后使用Unsega对Options处理，通过支持ExFat格式的7zip对vhd进行解压，并自动将文件重命名为游戏可直接读取的格式。

TIPS:

如果数字版本出现更新变动后无法获取到新版opt，请在get_download_ur用法中找到payload，并将title_ver修改到最新版本即可。

