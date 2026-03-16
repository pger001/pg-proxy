#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试工具：检查 Gateway 配置和连接
"""

import asyncio
import yaml
import sys
from pathlib import Path
import asyncpg
from typing import Dict, Any

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 60}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{text:^60}{Colors.END}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'=' * 60}{Colors.END}\n")

def print_success(text: str):
    print(f"{Colors.GREEN}✓{Colors.END} {text}")

def print_error(text: str):
    print(f"{Colors.RED}✗{Colors.END} {text}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}!{Colors.END} {text}")

def print_info(text: str):
    print(f"  {text}")


async def test_database_connection(config: Dict[str, Any]) -> bool:
    """测试数据库连接"""
    print_header("测试数据库连接")
    
    backend = config['backend']
    print_info(f"连接到: {backend['host']}:{backend['port']}/{backend['database']}")
    print_info(f"用户: {backend['user']}")
    
    try:
        conn = await asyncpg.connect(
            host=backend['host'],
            port=backend['port'],
            database=backend['database'],
            user=backend['user'],
            password=backend['password'],
            timeout=5
        )
        
        # 测试查询
        version = await conn.fetchval('SELECT version()')
        print_success(f"连接成功")
        print_info(f"PostgreSQL: {version.split(',')[0]}")
        
        # 检查 EXPLAIN 权限
        try:
            await conn.fetchval("EXPLAIN (FORMAT JSON) SELECT 1")
            print_success("EXPLAIN 权限正常")
        except Exception as e:
            print_error(f"EXPLAIN 权限不足: {e}")
            return False
        
        await conn.close()
        return True
        
    except Exception as e:
        print_error(f"连接失败: {e}")
        return False


async def test_tenant_extraction():
    """测试租户提取"""
    print_header("测试租户提取")
    
    from proxy_pool import TenantTracker
    
    tracker = TenantTracker(None, "test.log", False)
    
    test_cases = [
        ("SELECT * FROM orders WHERE tenant_code = 'T001'", "T001"),
        ("SELECT * FROM users WHERE tenant_id = 'T002' AND status = 'active'", "T002"),
        ("WITH data AS (SELECT * FROM orders WHERE tenant_code='T003') SELECT * FROM data", "T003"),
        ("SELECT * FROM products", None),
    ]
    
    all_passed = True
    for sql, expected in test_cases:
        result = tracker.extract_tenant_code(sql)
        if result == expected:
            print_success(f"提取成功: {sql[:50]}... -> {result}")
        else:
            print_error(f"提取失败: {sql[:50]}... (期望: {expected}, 得到: {result})")
            all_passed = False
    
    return all_passed


async def test_md5_cache():
    """测试 MD5 缓存"""
    print_header("测试 MD5 缓存")
    
    from proxy_pool import TenantTracker
    
    tracker = TenantTracker(None, "test.log")
    
    # 相同 SQL 的不同格式
    sql1 = "SELECT * FROM orders WHERE tenant_code = 'T001'"
    sql2 = "SELECT  *  FROM  orders  WHERE  tenant_code='T001'"
    sql3 = "select * from orders where tenant_code = 'T001'"
    
    md5_1 = tracker.calculate_sql_md5(sql1)
    md5_2 = tracker.calculate_sql_md5(sql2)
    md5_3 = tracker.calculate_sql_md5(sql3)
    
    print_info(f"SQL 1: {sql1}")
    print_info(f"MD5 1: {md5_1}")
    print_info(f"SQL 2: {sql2}")
    print_info(f"MD5 2: {md5_2}")
    print_info(f"SQL 3: {sql3}")
    print_info(f"MD5 3: {md5_3}")
    
    if md5_1 == md5_2 == md5_3:
        print_success("MD5 缓存标准化正常")
        return True
    else:
        print_error("MD5 缓存标准化失败")
        return False


async def test_config_file():
    """测试配置文件"""
    print_header("检查配置文件")
    
    config_file = Path('config.yaml')
    
    if not config_file.exists():
        print_error("config.yaml 不存在")
        return None
    
    print_success("config.yaml 存在")
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 检查必需字段
        required_fields = {
            'gateway': ['listen_host', 'listen_port', 'max_connections'],
            'backend': ['host', 'port', 'database', 'user', 'password'],
            'logging': ['log_file', 'enable_cache']
        }
        
        all_ok = True
        for section, fields in required_fields.items():
            if section not in config:
                print_error(f"缺少配置节: {section}")
                all_ok = False
                continue
            
            for field in fields:
                if field not in config[section]:
                    print_error(f"缺少配置项: {section}.{field}")
                    all_ok = False
                else:
                    print_success(f"{section}.{field} = {config[section][field]}")
        
        if all_ok:
            return config
        else:
            return None
            
    except Exception as e:
        print_error(f"配置文件解析失败: {e}")
        return None


async def test_dependencies():
    """测试依赖"""
    print_header("检查依赖包")
    
    required_modules = [
        'asyncpg',
        'aiofiles',
        'yaml',
        'fastapi',
        'uvicorn'
    ]
    
    all_ok = True
    for module in required_modules:
        try:
            __import__(module)
            print_success(f"{module} 已安装")
        except ImportError:
            print_error(f"{module} 未安装")
            all_ok = False
    
    return all_ok


async def main():
    """主测试流程"""
    print(f"\n{Colors.BOLD}PostgreSQL Gateway - 配置测试{Colors.END}")
    
    # 1. 检查依赖
    deps_ok = await test_dependencies()
    if not deps_ok:
        print_warning("\n请运行: pip install -r requirements.txt")
        return False
    
    # 2. 检查配置文件
    config = await test_config_file()
    if not config:
        return False
    
    # 3. 测试数据库连接
    db_ok = await test_database_connection(config)
    if not db_ok:
        return False
    
    # 4. 测试租户提取
    tenant_ok = await test_tenant_extraction()
    
    # 5. 测试 MD5 缓存
    cache_ok = await test_md5_cache()
    
    # 总结
    print_header("测试总结")
    
    all_ok = deps_ok and config and db_ok and tenant_ok and cache_ok
    
    if all_ok:
        print_success("所有测试通过！")
        print_info("\n现在可以运行:")
        print_info("  python app_example.py    # 示例应用")
        print_info("  python api_example.py    # Web API")
        print_info("  python proxy_pool.py     # 连接池演示")
        return True
    else:
        print_error("部分测试失败，请检查配置")
        return False


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}测试中断{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}测试出错: {e}{Colors.END}")
        sys.exit(1)
