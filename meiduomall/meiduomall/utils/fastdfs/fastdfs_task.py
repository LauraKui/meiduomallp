from fdfs_client.client import Fdfs_client

# 创建对象
client = Fdfs_client('./client.conf')
ret = client.upload_by_filename('/home/python/Desktop/20180716102024_V3AWj.jpeg')

print(ret)
# {
#     'Group name': 'group1',
#     'Remote file_id': 'group1/M00/00/00/wKhug1zOn5GAGbM0AAC4j90Tziw02.jpeg',
#     'Status': 'Upload successed.',
#     'Local file name': '/home/python/Desktop/upload_Images/01.jpeg',
#     'Uploaded size': '46.00KB',
#     'Storage IP': '192.168.110.131'}
