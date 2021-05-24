
import sys
import glob, os
import configparser
import pypandoc
import array
import shutil
from typing import NamedTuple
from datetime import datetime
from rfeed import *


output_target = "null"
input_target = "null"
conf_target = "null"
template_bottom_path = "template/bottom.html"
template_top_path = "template/top.html"
index_template_bottom_path = "template/index_bottom.html"
index_template_top_path = "template/index_top.html"

blog_config = configparser.ConfigParser()

class article_info:
    title: str
    writer: str
    date: str
    path: str
    path_ex: str
    resume: str
    
    def __init__(self, title, writer, date, path, resume, path_ex):
        self.path = path
        self.path_ex = path_ex
        self.title = title
        self.date = date
        self.writer = writer
        self.resume = resume


article_list = []

def create_rss_feed():
    global article_list
    rss_item_array = []
    for info in article_list:
        final_link = blog_config["blog"].get("link")+info.path_ex
        item = Item(
            title=info.title,
            link=final_link,
            description=info.resume,
            author=info.writer,
            guid=Guid(final_link),
            pubDate=  datetime.strptime(info.date, '%d %b %Y')
        )
        rss_item_array.append(item)

    feed = Feed(
        title=blog_config["blog"].get("blog_name"),
        link=blog_config["blog"].get("link")+"rss.xml",
        description=blog_config["blog"].get("sum"),
        language="en-US",
        lastBuildDate=datetime.now(),
        items=rss_item_array)

    
    with open("build/rss.xml", "w+") as xml_file:
        xml_file.truncate(0)
        xml_file.write(feed.rss())
        xml_file.close()
        

def read_config(config_path):

    blog_post_title = "unnamed"
    blog_post_date = "unknown"
    blog_post_writer = "anon"
    blog_post_resume = ""
    
    config = configparser.ConfigParser()
    config.read(config_path)
    if 'info' in config:
        
        if "title" in config["info"]:
            blog_post_title = config["info"].get("title")
            print(f"blog post title: {blog_post_title}")
        
        if "date" in config["info"]:
            blog_post_date = config["info"].get("date")
            print(f"blog post date: {blog_post_date}")
        
        if "author" in config["info"]:
            blog_post_writer = config["info"].get("author")
            print(f"blog post writer: {blog_post_writer}")
        if "resume" in config["info"]:
            blog_post_resume = config["info"].get("resume")
            print(f"blog post resume: {blog_post_resume}")
    else:
        print(f"not founded config file: {config_path}")
    
    return article_info(blog_post_title, blog_post_writer, blog_post_date, "null", blog_post_resume, "null")

def replace_config( file, config):
    file.seek(0)
    data = file.read()
    data = data.replace("{{writer}}",config.writer)
    data = data.replace("{{date}}", config.date)
    data = data.replace("{{title}}", config.title)
    file.seek(0)
    file.truncate(0)
    file.write(data)

def build_page(markdown_html, output_path, config_path, final_path):
    global article_list
    config = read_config(config_path)
    config.path = output_path
    config.path_ex = final_path
    article_list.append(config)

    with open(template_bottom_path, "r") as file1:
        template_bottom = file1.readlines()

    with open(template_top_path, "r") as file2:
        template_top = file2.readlines()

    with open(output_path, "w+") as file3:
        file3.writelines(template_top)
        file3.writelines(markdown_html)
        file3.writelines(template_bottom)
        replace_config(file3, config)

    file1.close()
    file2.close()
    file3.close()


def convert_page(markdown_path):
    return pypandoc.convert_file(markdown_path, 'html', format='md')

def copy_assets():
    for file in os.listdir("./assets"):
        shutil.copy2(os.path.join("./assets/", file), "./build/assets/")

    if "robots" in blog_config["blog"]:
        shutil.copy2(os.path.join("./src/", blog_config["blog"].get("robots")), "./build/robots.txt")
    
    if "about" in blog_config["blog"]:
        shutil.copy2(os.path.join("./src/", blog_config["blog"].get("about")), "./build/about.html")

    if "not_found" in blog_config["blog"]:
        shutil.copy2(os.path.join("./src/", blog_config["blog"].get("not_found")), "./build/notfound.html")

def init_path():
    if not os.path.exists("./build/"):
        os.mkdir("build")
    if not os.path.exists("./build/assets"):
        os.mkdir("build/assets")
    

def replace_index_template_info( data_in, file_out, config):
    data = data_in
    data = data.replace("{{writer}}",config.writer)
    data = data.replace("{{date}}", config.date)
    data = data.replace("{{title}}", config.title)
    data = data.replace("{{resume}}", config.resume)
    data = data.replace("{{path}}", config.path_ex)
    file_out.write(data)

def replace_file_out_info(file_out, config):
    file_out.seek(0)
    data = file_out.read()

    if "blog_name" in config["blog"]:
        data = data.replace("{{blog_name}}",config["blog"].get("blog_name"))

    if "sum" in config["blog"]:
        data = data.replace("{{sum}}",config["blog"].get("sum"))

    if "source_code" in config["blog"]:
        data = data.replace("{{source}}",config["blog"].get("source_code"))
    
    file_out.truncate(0)
    file_out.write(data)

def build_index_file():
    global article_list
    global blog_config

    article_list.sort(key = lambda entry: datetime.strptime(entry.date, '%d %b %Y'))
    article_list.reverse()
    article_entry_template = "./template/article_entry.html"

    with open(article_entry_template, "r") as article_entry_template_file:
        article_template = article_entry_template_file.read()

    with open(index_template_bottom_path, "r") as bottom_template_file:
        template_bottom = bottom_template_file.readlines()

    with open(index_template_top_path, "r") as top_template_file:
        template_top = top_template_file.readlines()
    
    output_file = open("build/index.html", "w+")
    output_file.truncate(0)

    output_file.writelines(template_top)
    
    for info in article_list:
        print(f"{info.title}")
        replace_index_template_info(article_template, output_file, info)
    
    output_file.writelines(template_bottom)
    
    article_entry_template_file.close()
    
    replace_file_out_info(output_file, blog_config)

    output_file.close()
    bottom_template_file.close()
    top_template_file.close()


if __name__ == "__main__":

    init_path()
    blog_config.read("src/blog_conf.conf")
    copy_assets()
    
    
    for file in os.listdir("./src"):
        if file.endswith(".md"):
            input_target = os.path.join("./src/", file)
            conf_target = os.path.join("./src/", file.replace(".md", ".conf"))
            output_target = os.path.join("./build/", file.replace(".md", ".html"))
            
            converted = convert_page(input_target)
            build_page(converted, output_target, conf_target, file.replace(".md", ".html"))
            print(f"created page: {output_target}")

    build_index_file()

    create_rss_feed()


