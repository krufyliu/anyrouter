#!/usr/bin/env python3
"""
AnyRouter.top 自动签到脚本
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from notify import notify

load_dotenv()


def load_accounts():
	"""从环境变量加载多账号配置"""
	accounts_str = os.getenv('ANYROUTER_ACCOUNTS')
	if not accounts_str:
		print('ERROR: ANYROUTER_ACCOUNTS environment variable not found')
		return None

	try:
		accounts_data = json.loads(accounts_str)

		# 检查是否为数组格式
		if not isinstance(accounts_data, list):
			print('ERROR: Account configuration must use array format [{}]')
			return None

		# 验证账号数据格式
		for i, account in enumerate(accounts_data):
			if not isinstance(account, dict):
				print(f'ERROR: Account {i + 1} configuration format is incorrect')
				return None
			if 'cookies' not in account or 'api_user' not in account:
				print(f'ERROR: Account {i + 1} missing required fields (cookies, api_user)')
				return None

		return accounts_data
	except Exception as e:
		print(f'ERROR: Account configuration format is incorrect: {e}')
		return None


def parse_cookies(cookies_data):
	"""解析 cookies 数据"""
	if isinstance(cookies_data, dict):
		return cookies_data

	if isinstance(cookies_data, str):
		cookies_dict = {}
		for cookie in cookies_data.split(';'):
			if '=' in cookie:
				key, value = cookie.strip().split('=', 1)
				cookies_dict[key] = value
		return cookies_dict
	return {}


async def get_waf_cookies_with_playwright(account_name: str):
	"""使用 Playwright 获取 WAF cookies（隐私模式）"""
	print(f'[PROCESSING] {account_name}: Starting browser to get WAF cookies...')

	async with async_playwright() as p:
		context = await p.chromium.launch_persistent_context(
			user_data_dir=None,
			headless=False,
			user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
			viewport={'width': 1920, 'height': 1080},
			args=[
				'--disable-blink-features=AutomationControlled',
				'--disable-dev-shm-usage',
				'--disable-web-security',
				'--disable-features=VizDisplayCompositor',
				'--no-sandbox',
			],
		)

		page = await context.new_page()

		try:
			print(f'[PROCESSING] {account_name}: Step 1: Access login page to get initial cookies...')

			await page.goto('https://anyrouter.top/login', wait_until='networkidle')

			try:
				await page.wait_for_function('document.readyState === "complete"', timeout=5000)
			except Exception:
				await page.wait_for_timeout(3000)

			cookies = await page.context.cookies()

			waf_cookies = {}
			for cookie in cookies:
				if cookie['name'] in ['acw_tc', 'cdn_sec_tc', 'acw_sc__v2']:
					waf_cookies[cookie['name']] = cookie['value']

			print(f'[INFO] {account_name}: Got {len(waf_cookies)} WAF cookies after step 1')

			required_cookies = ['acw_tc', 'cdn_sec_tc', 'acw_sc__v2']
			missing_cookies = [c for c in required_cookies if c not in waf_cookies]

			if missing_cookies:
				print(f'[FAILED] {account_name}: Missing WAF cookies: {missing_cookies}')
				await context.close()
				return None

			print(f'[SUCCESS] {account_name}: Successfully got all WAF cookies')

			await context.close()

			return waf_cookies

		except Exception as e:
			print(f'[FAILED] {account_name}: Error occurred while getting WAF cookies: {e}')
			await context.close()
			return None


def get_user_info(client, headers):
	"""获取用户信息"""
	try:
		response = client.get('https://anyrouter.top/api/user/self', headers=headers, timeout=30)

		if response.status_code == 200:
			data = response.json()
			if data.get('success'):
				user_data = data.get('data', {})
				quota = round(user_data.get('quota', 0) / 500000, 2)
				used_quota = round(user_data.get('used_quota', 0) / 500000, 2)
				return {
					'quota': quota,
					'used_quota': used_quota,
					'display_text': f'💰 Current balance: ${quota}, Used: ${used_quota}'
				}
	except Exception as e:
		return {
			'error': str(e),
			'display_text': f'[FAIL] Failed to get user info: {str(e)[:50]}...'
		}
	return None


async def check_in_account(account_info, account_index):
	"""为单个账号执行签到操作"""
	account_name = f'Account {account_index + 1}'
	print(f'\n[PROCESSING] Starting to process {account_name}')

	# 解析账号配置
	cookies_data = account_info.get('cookies', {})
	api_user = account_info.get('api_user', '')

	if not api_user:
		print(f'[FAILED] {account_name}: API user identifier not found')
		return False, None

	# 解析用户 cookies
	user_cookies = parse_cookies(cookies_data)
	if not user_cookies:
		print(f'[FAILED] {account_name}: Invalid configuration format')
		return False, None

	# 步骤1：获取 WAF cookies
	waf_cookies = await get_waf_cookies_with_playwright(account_name)
	if not waf_cookies:
		print(f'[FAILED] {account_name}: Unable to get WAF cookies')
		return False, None

	# 步骤2：使用 httpx 进行 API 请求
	client = httpx.Client(http2=True, timeout=30.0)

	try:
		# 合并 WAF cookies 和用户 cookies
		all_cookies = {**waf_cookies, **user_cookies}
		client.cookies.update(all_cookies)

		headers = {
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
			'Accept': 'application/json, text/plain, */*',
			'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
			'Accept-Encoding': 'gzip, deflate, br, zstd',
			'Referer': 'https://anyrouter.top/console',
			'Origin': 'https://anyrouter.top',
			'Connection': 'keep-alive',
			'Sec-Fetch-Dest': 'empty',
			'Sec-Fetch-Mode': 'cors',
			'Sec-Fetch-Site': 'same-origin',
			'new-api-user': api_user,
		}

		# 获取签到前的用户信息
		user_info_before = get_user_info(client, headers)
		user_info_text = "信息获取失败"

		if user_info_before and 'display_text' in user_info_before:
			print(user_info_before['display_text'])

		print(f'[NETWORK] {account_name}: Executing check-in')

		# 更新签到请求头
		checkin_headers = headers.copy()
		checkin_headers.update({'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'})

		response = client.post('https://anyrouter.top/api/user/sign_in', headers=checkin_headers, timeout=30)

		print(f'[RESPONSE] {account_name}: Response status code {response.status_code}')

		# 获取签到后的用户信息
		user_info_after = get_user_info(client, headers)

		# 构建详细的用户信息文本
		if user_info_before and user_info_after:
			# 如果两次都获取成功，显示详细对比
			before_quota = user_info_before.get('quota', 0)
			before_used = user_info_before.get('used_quota', 0)
			after_quota = user_info_after.get('quota', 0)
			after_used = user_info_after.get('used_quota', 0)

			# 计算签到奖励
			reward = after_quota - before_quota

			user_info_text = f"""🆔 账户ID: {api_user}
💰 签到前余额: ${before_quota}, 已用: ${before_used}
💰 签到后余额: ${after_quota}, 已用: ${after_used}
🎁 签到奖励: 💰{reward}"""
		elif user_info_before:
			# 只有签到前信息
			user_info_text = f"🆔 账户ID: {api_user}\n" + user_info_before.get('display_text', '信息获取失败')
		elif user_info_after:
			# 只有签到后信息
			user_info_text = f"🆔 账户ID: {api_user}\n" + user_info_after.get('display_text', '信息获取失败')

		if response.status_code == 200:
			try:
				result = response.json()
				if result.get('ret') == 1 or result.get('code') == 0 or result.get('success'):
					print(f'[SUCCESS] {account_name}: Check-in successful!')
					return True, user_info_text
				else:
					error_msg = result.get('msg', result.get('message', 'Unknown error'))
					print(f'[FAILED] {account_name}: Check-in failed - {error_msg}')
					return False, user_info_text
			except json.JSONDecodeError:
				# 如果不是 JSON 响应，检查是否包含成功标识
				if 'success' in response.text.lower():
					print(f'[SUCCESS] {account_name}: Check-in successful!')
					return True, user_info_text
				else:
					print(f'[FAILED] {account_name}: Check-in failed - Invalid response format')
					return False, user_info_text
		else:
			print(f'[FAILED] {account_name}: Check-in failed - HTTP {response.status_code}')
			return False, user_info_text

	except Exception as e:
		error_msg = f'Error occurred during check-in process - {str(e)[:50]}...'
		print(f'[FAILED] {account_name}: {error_msg}')
		user_info_text = f'🆔 账户ID: {api_user}\n❌ 处理异常: {str(e)[:50]}...'
		return False, user_info_text
	finally:
		client.close()


async def main():
	"""主函数"""
	# 设置时区
	tz = ZoneInfo('Asia/Shanghai')
	start_time = datetime.now(tz)

	print('[SYSTEM] AnyRouter.top multi-account auto check-in script started (using Playwright)')
	print(f'[TIME] Execution time: {start_time.strftime("%Y-%m-%d %H:%M:%S")}')

	# 加载账号配置
	accounts = load_accounts()
	if not accounts:
		print('[FAILED] Unable to load account configuration, program exits')
		sys.exit(1)

	print(f'[INFO] Found {len(accounts)} account configurations')

	# 为每个账号执行签到
	success_count = 0
	total_count = len(accounts)
	notification_content = []

	for i, account in enumerate(accounts):
		try:
			success, user_info = await check_in_account(account, i)
			if success:
				success_count += 1
			# 收集通知内容
			status = '✅' if success else '❌'
			account_result = f'{status} Account {i + 1}'
			if user_info:
				account_result += f'\n{user_info}'
			notification_content.append(account_result)
		except Exception as e:
			print(f'[FAILED] Account {i + 1} processing exception: {e}')
			notification_content.append(f'❌ Account {i + 1} exception: {str(e)[:50]}...')

	# 构建通知内容
	end_time = datetime.now(tz)
	time_info = f'⏰ 执行时间: {end_time.strftime("%Y-%m-%d %H:%M:%S %Z")}'

	# 构建详细的邮件内容
	email_content = [
		'📧 AnyRouter 多账号自动签到报告',
		'=' * 40,
		time_info,
		'',
		'📊 账号详情:',
		'-' * 20,
	]

	# 添加每个账号的详细信息
	if notification_content:
		for content in notification_content:
			email_content.append(content)
			email_content.append('')
	else:
		email_content.append('❌ 未获取到账号信息')
		email_content.append('')

	# 添加统计摘要
	email_content.extend([
		'📈 统计摘要:',
		'-' * 20,
		f'✅ 签到成功: {success_count}/{total_count}',
		f'❌ 签到失败: {total_count - success_count}/{total_count}',
		''
	])

	if success_count == total_count:
		result_status = '成功'
		email_content.append('🎉 所有账号签到成功！')
	elif success_count > 0:
		result_status = '部分成功'
		email_content.append('⚠️  部分账号签到成功')
	else:
		result_status = '失败'
		email_content.append('🚨 所有账号签到失败')

	email_content.append('')
	email_content.append('📱 本邮件由AnyRouter自动签到脚本发送')

	formatted_content = '\n'.join(email_content)

	print(formatted_content)

	# 创建动态标题
	title = f'AnyRouter 签到{result_status} ({success_count}/{total_count}) - {end_time.strftime("%Y-%m-%d %H:%M:%S")}'

	notify.push_message(title, formatted_content, msg_type='text')

	# 设置退出码
	sys.exit(0 if success_count > 0 else 1)


def run_main():
	"""运行主函数的包装函数"""
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		print('\n[WARNING] Program interrupted by user')
		sys.exit(1)
	except Exception as e:
		print(f'\n[FAILED] Error occurred during program execution: {e}')
		sys.exit(1)


if __name__ == '__main__':
	run_main()
