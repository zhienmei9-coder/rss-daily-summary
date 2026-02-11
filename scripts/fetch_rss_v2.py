#!/usr/bin/env python3
"""
RSS 每日摘要生成器 - 重构版本 v2
改进：日志系统、错误处理、测试模式、健康检查
"""

# ============================================================================
# 配置和导入
# ============================================================================

import ssl
import urllib.request
import os
import sys
import hashlib
import xml.etree.ElementTree as ET
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
import feedparser
import html

# 配置 SSL 上下文
ssl._create_default_https_context = ssl._create_unverified_context

# ============================================================================
# 配置类
# ============================================================================

@dataclass
class Config:
    """所有配置集中在这里"""
    # 文件路径
    opml_file: str = "opml/feeds.opml"
    db_file: str = ".rss/articles.db"
    output_dir: str = "Daily RSS"
    log_file: str = ".rss/fetch.log"

    # 功能开关
    enable_translation: bool = True
    max_article_age_hours: int = 48
    max_articles_per_feed: int = 3

    # 输出格式
    max_desc_length: int = 300
    translate_max_length: int = 5000

    # 测试模式
    test_mode: bool = False
    dry_run: bool = False

# ============================================================================
# 日志系统
# ============================================================================

class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""
    COLORS = {
        'DEBUG': '\033[36m',    # 青色
        'INFO': '\033[32m',     # 绿色
        'WARNING': '\033[33m',  # 黄色
        'ERROR': '\033[31m',    # 红色
        'CRITICAL': '\033[35m', # 紫色
    }
    RESET = '\033[0m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, '')
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)

def setup_logging(config: Config) -> logging.Logger:
    """设置日志系统"""
    logger = logging.getLogger('rss_fetcher')
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()  # 清除已有的处理器

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = ColoredFormatter(
        '%(levelname)s | %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    log_path = Path(config.log_file)
    log_path.parent.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger

# ============================================================================
# 数据库类（改进版）
# ============================================================================

class ArticleDB:
    """文章数据库 - 改进版"""

    def __init__(self, db_file: str, logger: logging.Logger, test_mode: bool = False):
        self.db_file = Path(db_file)
        self.logger = logger
        self.test_mode = test_mode
        self.seen = set()
        self._load()

    def _load(self):
        """加载数据库"""
        if self.db_file.exists():
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    self.seen = set(line.strip() for line in f if line.strip())
                self.logger.debug(f"加载数据库: {len(self.seen)} 条记录")
            except Exception as e:
                self.logger.error(f"数据库加载失败: {e}")
                self.seen = set()
        else:
            self.logger.debug("数据库文件不存在，创建新数据库")

    def save(self):
        """保存数据库（只在非测试模式下）"""
        if not self.test_mode:
            try:
                self.db_file.parent.mkdir(exist_ok=True)
                with open(self.db_file, 'w', encoding='utf-8') as f:
                    for item in self.seen:
                        f.write(f"{item}\n")
                self.logger.debug(f"数据库已保存: {len(self.seen)} 条记录")
            except Exception as e:
                self.logger.error(f"数据库保存失败: {e}")

    def is_seen(self, url: str) -> bool:
        """检查 URL 是否已见过"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return url_hash in self.seen

    def add(self, url: str) -> bool:
        """添加 URL 到数据库，返回是否为新添加"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        is_new = url_hash not in self.seen
        if is_new:
            self.seen.add(url_hash)
        return is_new

    def count(self) -> int:
        """返回数据库中的记录数"""
        return len(self.seen)

# ============================================================================
# 翻译功能（改进版）
# ============================================================================

class Translator:
    """翻译器 - 改进版"""

    def __init__(self, config: Config, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.available = False
        self._init_translator()

    def _init_translator(self):
        """初始化翻译器"""
        if not self.config.enable_translation:
            self.logger.info("翻译功能已禁用")
            return

        try:
            from deep_translator import GoogleTranslator
            self.translator = GoogleTranslator(source='auto', target='zh-CN')
            self.available = True
            self.logger.info("翻译器初始化成功")
        except ImportError:
            self.logger.warning("翻译库未安装，跳过翻译")
        except Exception as e:
            self.logger.warning(f"翻译器初始化失败: {e}")

    def translate(self, text: str) -> str:
        """翻译文本"""
        if not text or not self.available:
            return text

        # 检查是否已包含中文
        if any('\u4e00' <= c <= '\u9fff' for c in text):
            return text

        # 清理 HTML
        import re
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        if not text:
            return text

        # 限制长度
        if len(text) > self.config.translate_max_length:
            text = text[:self.config.translate_max_length]

        try:
            return self.translator.translate(text)
        except Exception as e:
            self.logger.warning(f"翻译失败: {e}")
            return text

# ============================================================================
# 时间过滤（改进版）
# ============================================================================

def is_article_recent(parsed_time_struct, max_hours: int) -> Tuple[bool, Optional[datetime], str]:
    """
    检查文章是否在指定时间范围内
    返回: (是否在范围内, 解析后的日期, 信息)
    """
    if not parsed_time_struct:
        return (False, None, "无发布日期")

    try:
        # 将 time_struct 转换为 datetime
        parsed_date = datetime(*parsed_time_struct[:6])
        time_diff = datetime.now() - parsed_date
        hours_old = time_diff.total_seconds() / 3600

        is_recent = hours_old <= max_hours
        info = f"{hours_old:.1f}小时前"
        return (is_recent, parsed_date, info)

    except Exception as e:
        return (False, None, f"日期解析错误: {e}")

# ============================================================================
# OPML 解析
# ============================================================================

def parse_opml(opml_file: str, logger: logging.Logger) -> List[Dict[str, str]]:
    """解析 OPML 文件，返回 RSS 源列表"""
    logger.info(f"解析 OPML 文件: {opml_file}")

    if not Path(opml_file).exists():
        raise FileNotFoundError(f"OPML 文件不存在: {opml_file}")

    tree = ET.parse(opml_file)
    root = tree.getroot()
    sources = []

    # 尝试带命名空间的查找
    for outline in root.findall('.//{http://www.guyrutenberg.com/2008/opml}outline'):
        rss_url = outline.get('xmlUrl', '')
        blog_name = outline.get('text', outline.get('title', 'Unknown'))
        if rss_url:
            sources.append({'name': blog_name, 'url': rss_url})

    # 如果没找到，尝试不带命名空间
    if not sources:
        for outline in root.findall('.//outline'):
            rss_url = outline.get('xmlUrl', '')
            blog_name = outline.get('text', outline.get('title', 'Unknown'))
            if rss_url:
                sources.append({'name': blog_name, 'url': rss_url})

    logger.info(f"找到 {len(sources)} 个 RSS 源")
    return sources

# ============================================================================
# 文章数据类
# ============================================================================

@dataclass
class Article:
    """文章数据类"""
    blog: str
    title: str
    link: str
    desc: str
    date: str
    date_info: str = ""

# ============================================================================
# 文章抓取
# ============================================================================

def fetch_articles(config: Config, db: ArticleDB, translator: Translator, logger: logging.Logger) -> Dict[str, Any]:
    """抓取所有文章"""
    sources = parse_opml(config.opml_file, logger)

    articles = []
    stats = {
        'new': 0,
        'seen': 0,
        'old': 0,
        'errors': 0,
        'sources_success': 0,
        'sources_failed': 0,
    }

    for i, source in enumerate(sources, 1):
        logger.info(f"[{i}/{len(sources)}] 抓取: {source['name']}")

        try:
            feed = feedparser.parse(source['url'])
            entries_count = 0

            for entry in feed.entries[:config.max_articles_per_feed]:
                try:
                    link = entry.get('link', '')
                    if not link:
                        continue

                    # 检查是否重复
                    if db.is_seen(link):
                        stats['seen'] += 1
                        logger.debug(f"  跳过（重复）: {entry.get('title', 'No title')[:50]}")
                        continue

                    # 检查时间
                    published_parsed = entry.get('published_parsed') or entry.get('updated_parsed')
                    published = entry.get('published') or entry.get('updated', '')

                    is_recent, parsed_date, date_info = is_article_recent(
                        published_parsed,
                        config.max_article_age_hours
                    )

                    if not is_recent:
                        stats['old'] += 1
                        db.add(link)  # 加入数据库避免下次重复检查
                        logger.debug(f"  跳过（过旧）: {date_info}")
                        continue

                    # 接受文章
                    db.add(link)
                    stats['new'] += 1

                    # 获取内容
                    title = entry.get('title', 'No title')
                    description = entry.get('description', '')

                    # 翻译
                    if translator.available:
                        title = translator.translate(title)
                        description = translator.translate(description)

                    # 截断描述
                    if description and len(description) > config.max_desc_length:
                        description = description[:config.max_desc_length] + "..."

                    article = Article(
                        blog=source['name'],
                        title=title,
                        link=link,
                        desc=description,
                        date=published,
                        date_info=date_info
                    )
                    articles.append(article)
                    entries_count += 1
                    logger.debug(f"  + {title[:50]}")

                except Exception as e:
                    logger.error(f"  文章处理错误: {e}")
                    stats['errors'] += 1

            stats['sources_success'] += 1
            if entries_count > 0:
                logger.info(f"  ✓ 新增 {entries_count} 篇文章")

        except Exception as e:
            logger.error(f"  RSS 源错误: {e}")
            stats['sources_failed'] += 1
            stats['errors'] += 1

    return {'articles': articles, 'stats': stats}

# ============================================================================
# Markdown 生成
# ============================================================================

def generate_markdown(articles: List[Article], stats: Dict[str, Any], config: Config, sources_total: int) -> str:
    """生成 Markdown 内容"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H:%M")

    # 计算 db_total
    db_total = stats['new'] + stats['seen'] + stats['old']

    content = f"""# RSS 每日摘要 - {date_str}

> 生成时间: {date_str} {time_str}
> 🌐 已自动翻译为中文
> ⏰ 仅显示最近 {config.max_article_age_hours} 小时内的文章

## 📊 今日统计

- 🆕 新文章: {stats['new']}
- 📋 已跳过（重复）: {stats['seen']}
- ⏰ 已跳过（过旧）: {stats['old']}
- 📚 数据库总文章: {db_total}
- ⚠️ 错误数: {stats['errors']}
- ✅ 成功源: {stats['sources_success']}/{sources_total}

---

## 📡 今日更新

"""

    # 按博客分组
    by_blog = {}
    for article in articles:
        if article.blog not in by_blog:
            by_blog[article.blog] = []
        by_blog[article.blog].append(article)

    for blog, blog_articles in by_blog.items():
        content += f"### 📌 {blog}\n\n"
        for article in blog_articles:
            content += f"- **{article.title}**\n"
            if article.desc:
                content += f"  > {article.desc}\n"
            content += f"  > 🔗 [阅读原文]({article.link})\n"
            if article.date:
                content += f"  > 📅 {article.date}\n"
            content += "\n"

    content += f"""

---

## 📊 统计信息

| 项目 | 数量 |
|------|------|
| 🆕 新文章 | {stats['new']} |
| 📋 已跳过（重复） | {stats['seen']} |
| ⏰ 已跳过（过旧） | {stats['old']} |
| ⚠️ 错误数 | {stats['errors']} |
| ✅ 成功源 | {stats['sources_success']}/{sources_total} |
| 📚 数据库总文章 | {db_total} |

- 生成时间: {date_str} {time_str}
- 时间范围: 最近 {config.max_article_age_hours} 小时
- 数据来源: [HN 2025 热门博客](https://gist.github.com/emschwartz/e6d2bf860ccc367fe37ff953ba6de66b)

## 🔖 标签

#DailyRSS #技术博客 #HackerNews #新文章 #{date_str} #中文翻译

---

*本笔记由 GitHub Actions 自动生成，内容已翻译为中文*
"""
    return content

# ============================================================================
# 主函数
# ============================================================================

def main():
    """主函数"""
    # 解析命令行参数
    config = Config()
    if '--test' in sys.argv:
        config.test_mode = True

    if '--dry-run' in sys.argv:
        config.dry_run = True

    # 设置日志
    logger = setup_logging(config)

    if config.test_mode:
        logger.info("🧪 测试模式已启用")
    if config.dry_run:
        logger.info("🔍 干运行模式已启用")

    logger.info("=" * 60)
    logger.info("RSS 每日摘要生成器启动")
    logger.info(f"配置: 翻译={config.enable_translation}, 时间范围={config.max_article_age_hours}小时")

    try:
        # 初始化
        db = ArticleDB(config.db_file, logger, test_mode=config.test_mode)
        translator = Translator(config, logger)

        # 抓取文章
        logger.info("开始抓取文章...")
        result = fetch_articles(config, db, translator, logger)

        # 保存数据库
        if not config.dry_run:
            db.save()
        else:
            logger.info("干运行模式：跳过数据库保存")

        # 生成 Markdown
        date_str = datetime.now().strftime("%Y-%m-%d")
        filepath = Path(config.output_dir) / f"RSS摘要_{date_str}.md"

        if not config.dry_run:
            content = generate_markdown(result['articles'], result['stats'], config, 92)

            Path(config.output_dir).mkdir(exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"✅ 文件已生成: {filepath}")
        else:
            logger.info("干运行模式：跳过文件生成")

        # 打印统计
        stats = result['stats']
        db_total = db.count()
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ 完成!")
        logger.info(f"  🆕 新文章: {stats['new']}")
        logger.info(f"  📋 已跳过（重复）: {stats['seen']}")
        logger.info(f"  ⏰ 已跳过（过旧）: {stats['old']}")
        logger.info(f"  ⚠️ 错误数: {stats['errors']}")
        logger.info(f"  📚 数据库总数: {db_total}")
        logger.info("=" * 60)

        return 0

    except Exception as e:
        logger.error(f"❌ 程序错误: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
