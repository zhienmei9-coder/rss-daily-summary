#!/usr/bin/env python3
"""
RSS 抓取脚本测试套件
验证核心功能是否正常工作
"""

import sys
import os
from datetime import datetime, timedelta

# 添加 scripts 目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_time_filter():
    """测试时间过滤功能"""
    print("🧪 测试时间过滤...")

    # 导入
    from fetch_rss_v2 import is_article_recent

    # 测试用例
    now = datetime.now()
    recent_time = (now - timedelta(hours=24)).timetuple()
    old_time = (now - timedelta(days=10)).timetuple()
    future_time = (now + timedelta(hours=1)).timetuple()

    tests = [
        (recent_time, 48, True, "24小时前的文章应该在48小时内"),
        (old_time, 48, False, "10天前的文章不应该在48小时内"),
        (future_time, 48, True, "未来的文章应该被接受"),
        (None, 48, False, "没有日期的文章应该被拒绝"),
    ]

    passed = 0
    failed = 0

    for time_struct, max_hours, expected, description in tests:
        is_recent, parsed_date, info = is_article_recent(time_struct, max_hours)
        if is_recent == expected:
            print(f"  ✅ {description}")
            passed += 1
        else:
            print(f"  ❌ {description}")
            print(f"     期望: {expected}, 实际: {is_recent}, 信息: {info}")
            failed += 1

    print(f"\n时间过滤测试: {passed} 通过, {failed} 失败")
    return failed == 0

def test_database():
    """测试数据库功能"""
    print("\n🧪 测试数据库...")

    from fetch_rss_v2 import ArticleDB
    import tempfile
    import logging

    # 创建一个简单的 logger
    logging.basicConfig(level=logging.WARNING)
    logger = logging.getLogger('test')

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db') as f:
        db_file = f.name

    try:
        db = ArticleDB(db_file, logger, test_mode=True)

        # 测试添加和检查
        test_urls = [
            "https://example.com/article1",
            "https://example.com/article2",
            "https://example.com/article3",
        ]

        for url in test_urls:
            db.add(url)

        # 验证
        passed = 0
        failed = 0

        if db.is_seen(test_urls[0]):
            print(f"  ✅ 添加的 URL 能被识别")
            passed += 1
        else:
            print(f"  ❌ 添加的 URL 未能被识别")
            failed += 1

        if not db.is_seen("https://example.com/notexist"):
            print(f"  ✅ 未添加的 URL 正确返回 False")
            passed += 1
        else:
            print(f"  ❌ 未添加的 URL 错误返回 True")
            failed += 1

        if db.count() == 3:
            print(f"  ✅ 计数正确: {db.count()}")
            passed += 1
        else:
            print(f"  ❌ 计数错误: 期望 3, 实际 {db.count()}")
            failed += 1

        # 测试重复添加
        db.add(test_urls[0])
        if db.count() == 3:
            print(f"  ✅ 重复添加不会增加计数")
            passed += 1
        else:
            print(f"  ❌ 重复添加增加了计数")
            failed += 1

        print(f"\n数据库测试: {passed} 通过, {failed} 失败")
        return failed == 0

    finally:
        import os
        if os.path.exists(db_file):
            os.unlink(db_file)

def test_config():
    """测试配置类"""
    print("\n🧪 测试配置...")

    from fetch_rss_v2 import Config

    config = Config()

    tests = [
        (config.max_article_age_hours == 48, "默认时间范围是 48 小时"),
        (config.enable_translation == True, "翻译默认启用"),
        (config.max_desc_length == 300, "默认描述长度 300"),
        (config.test_mode == False, "默认不是测试模式"),
    ]

    passed = sum(1 for t, _ in tests if t)
    failed = len(tests) - passed

    for test, description in tests:
        if test:
            print(f"  ✅ {description}")
        else:
            print(f"  ❌ {description}")

    print(f"\n配置测试: {passed} 通过, {failed} 失败")
    return failed == 0

def test_translation():
    """测试翻译功能"""
    print("\n🧪 测试翻译...")

    from fetch_rss_v2 import Translator, Config
    import logging

    logging.basicConfig(level=logging.WARNING)
    logger = logging.getLogger('test')

    config = Config()
    translator = Translator(config, logger)

    tests = [
        (translator.translate("Hello World") != "Hello World" or not translator.available,
         "英文文本应该被翻译（如果翻译可用）"),
        (translator.translate("你好世界") == "你好世界", "中文文本不应该被翻译"),
        (translator.translate("") == "", "空文本应该返回空"),
        (translator.translate(None) == None, "None 应该返回 None"),
    ]

    passed = 0
    failed = 0

    for test, description in tests:
        if test:
            print(f"  ✅ {description}")
            passed += 1
        else:
            print(f"  ❌ {description}")
            failed += 1

    print(f"\n翻译测试: {passed} 通过, {failed} 失败")
    return failed == 0

def main():
    """运行所有测试"""
    print("=" * 60)
    print("RSS 抓取脚本测试套件")
    print("=" * 60)

    results = {
        "时间过滤": test_time_filter(),
        "数据库": test_database(),
        "配置": test_config(),
        "翻译": test_translation(),
    }

    print("\n" + "=" * 60)
    print("测试结果汇总:")
    print("=" * 60)

    all_passed = True
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("⚠️  部分测试失败，请检查")
        return 1

if __name__ == "__main__":
    sys.exit(main())
