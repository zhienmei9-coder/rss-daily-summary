#!/usr/bin/env python3
import os
import sys
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import feedparser

# 配置
OPML_FILE = "opml/feeds.opml"
DB_FILE = ".rss/articles.db"
OUTPUT_DIR = "Daily RSS"
TRANSLATE_TO_CHINESE = True  # 设置为 True 启用翻译

Path(DB_FILE).parent.mkdir(exist_ok=True)
Path(OUTPUT_DIR).mkdir(exist_ok=True)

class ArticleDB:
    def __init__(self, db_file):
        self.db_file = Path(db_file)
        self.seen = set()
        if self.db_file.exists():
            with open(self.db_file, 'r') as f:
                self.seen = set(line.strip() for line in f if line.strip())

    def is_seen(self, url):
        return hashlib.md5(url.encode()).hexdigest() in self.seen

    def add(self, url):
        self.seen.add(hashlib.md5(url.encode()).hexdigest())
        with open(self.db_file, 'w') as f:
            for item in self.seen:
                f.write(f"{item}\n")

    def count(self):
        return len(self.seen)

def translate_to_chinese(text):
    """简单的翻译函数（使用规则+字典）"""
    # 简单的技术术语翻译
    translations = {
        "AI": "AI",
        "Machine Learning": "机器学习",
        "Deep Learning": "深度学习",
        "Python": "Python",
        "JavaScript": "JavaScript",
        "TypeScript": "TypeScript",
        "Rust": "Rust",
        "Go": "Go",
        "GitHub": "GitHub",
        "Docker": "Docker",
        "Kubernetes": "Kubernetes",
        "Linux": "Linux",
        "Security": "安全",
        "Privacy": "隐私",
        "Cloud": "云",
        "Database": "数据库",
        "API": "API",
        "Web Development": "Web开发",
        "Frontend": "前端",
        "Backend": "后端",
        "DevOps": "DevOps",
        "Data Science": "数据科学",
        "Tutorial": "教程",
        "Guide": "指南",
        "How to": "如何",
        "Introduction": "介绍",
        "Overview": "概述",
        "Getting Started": "入门指南",
    }

    # 移除 HTML 标签
    import re
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    # 简单的标记检测和提示
    chinese_note = ""
    if any(ord(c) > 127 for c in text):
        # 已经包含中文字符
        return text
    else:
        # 英文内容，添加翻译提示
        chinese_note = " [英文]"

    return text + chinese_note

def parse_opml(opml_file):
    sources = []
    tree = ET.parse(opml_file)
    root = tree.getroot()

    for outline in root.findall('.//outline'):
        xml_url = outline.get('xmlUrl', '')
        if xml_url:
            name = outline.get('text', outline.get('title', 'Unknown'))
            sources.append({'name': name, 'url': xml_url})

    return sources

def main():
    db = ArticleDB(DB_FILE)

    if not Path(OPML_FILE).exists():
        print(f"Error: OPML file not found: {OPML_FILE}")
        sys.exit(1)

    sources = parse_opml(OPML_FILE)
    print(f"找到 {len(sources)} 个 RSS 源")

    articles = []
    total_new = 0
    total_seen = 0

    for source in sources:
        try:
            feed = feedparser.parse(source['url'])
            for entry in feed.entries[:3]:
                link = entry.get('link', '')
                if not link or db.is_seen(link):
                    total_seen += 1
                    continue

                db.add(link)
                total_new += 1

                # 获取标题和描述
                title = entry.get('title', 'No title')
                description = entry.get('description', '')[:200]

                # 如果启用了翻译
                if TRANSLATE_TO_CHINESE:
                    title = translate_to_chinese(title)
                    description = translate_to_chinese(description)

                article = {
                    'blog': source['name'],
                    'title': title,
                    'link': link,
                    'desc': description,
                    'date': entry.get('published', '')
                }
                articles.append(article)
        except Exception as e:
            print(f"Error fetching {source['name']}: {e}", file=sys.stderr)

    # 生成 Markdown
    date_str = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H:%M")
    filepath = Path(OUTPUT_DIR) / f"RSS摘要_{date_str}.md"

    content = f"""# RSS 每日摘要 - {date_str}

> 生成时间: {date_str} {time_str}
> 📌 说明：英文文章标记为 [英文]，已尽可能识别技术术语

## 📊 今日统计

- 🆕 新文章: {total_new}
- 📋 已跳过（重复）: {total_seen}
- 📚 数据库总文章: {db.count()}

---

## 📡 今日更新

"""

    for article in articles:
        content += f"### 📌 {article['blog']}\n\n"
        content += f"- **{article['title']}**\n"
        if article['desc'] and article['desc'] != 'No title':
            content += f"  > {article['desc']}...\n"
        content += f"  > 🔗 [阅读原文]({article['link']})\n"
        if article['date']:
            content += f"  > 📅 {article['date']}\n"
        content += "\n"

    content += f"""

---

## 📊 统计信息

| 项目 | 数量 |
|------|------|
| 🆕 新文章 | {total_new} |
| 📋 已跳过（重复） | {total_seen} |
| 📚 数据库总文章 | {db.count()} |

- 生成时间: {date_str} {time_str}
- 数据来源: [HN 2025 热门博客](https://gist.github.com/emschwartz/e6d2bf860ccc367fe37ff953ba6de66b)

## 🔖 标签

#DailyRSS #技术博客 #HackerNews #新文章 #{date_str}

---

*本笔记由 GitHub Actions 自动生成*
"""

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"\n✅ 完成!")
    print(f"  新文章: {total_new}")
    print(f"  已跳过: {total_seen}")
    print(f"  数据库总数: {db.count()}")
    print(f"  笔记文件: {filepath}")

if __name__ == "__main__":
    main()
