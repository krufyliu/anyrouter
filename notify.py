import os
import ssl
import smtplib
from email.utils import formataddr, parseaddr
from email.mime.text import MIMEText
from email.header import Header
from typing import Literal

import httpx


class NotificationKit:
	def __init__(self):
		# 每次调用时重新读取环境变量，确保能获取到最新的配置
		self._reload_config()

	def _reload_config(self):
		"""重新加载配置"""
		self.email_user: str = os.getenv('EMAIL_USER', '')
		self.email_pass: str = os.getenv('EMAIL_PASS', '')
		self.email_to: str = os.getenv('EMAIL_TO', '')
		# 可选 SMTP 配置
		self.smtp_host: str | None = os.getenv('SMTP_HOST')
		self.smtp_port: str | None = os.getenv('SMTP_PORT')
		self.email_use_ssl: str | None = os.getenv('EMAIL_USE_SSL')
		self.smtp_timeout: float = float(os.getenv('SMTP_TIMEOUT', '30'))
		self.smtp_debug: bool = (os.getenv('SMTP_DEBUG', '0').lower() in ['1', 'true', 'yes'])
		self.pushplus_token = os.getenv('PUSHPLUS_TOKEN')
		self.server_push_key = os.getenv('SERVERPUSHKEY')
		self.dingding_webhook = os.getenv('DINGDING_WEBHOOK')
		self.feishu_webhook = os.getenv('FEISHU_WEBHOOK')
		self.weixin_webhook = os.getenv('WEIXIN_WEBHOOK')
		self.ntfy_server = os.getenv('NTFY_SERVER')

	def send_email(self, title: str, content: str, msg_type: Literal['text', 'html'] = 'text'):
		# 发送前重新加载配置，确保获取最新的环境变量
		self._reload_config()

		if not self.email_user or not self.email_pass or not self.email_to:
			raise ValueError('Email configuration not set')


		# 确保内容不为空
		if not content or len(content.strip()) == 0:
			content = "邮件内容为空，这是一个测试消息。"

		# 使用MIMEText直接创建邮件，而不是MIMEMultipart
		# 修复Content-Type问题：确保msg_type为'plain'或'html'
		content_type = 'plain' if msg_type == 'text' else msg_type
		msg = MIMEText(content, content_type, 'utf-8')
		# RFC 合规的 From/To/Subject
		from_name = 'AnyRouter 签到助手'
		from_addr = self.email_user
		# 避免非 ASCII 地址编码问题
		msg['From'] = formataddr((str(Header(from_name, 'utf-8')), from_addr))
		# To 只放地址，避免被 QQ 严格规则误判
		_, to_addr = parseaddr(self.email_to)
		msg['To'] = to_addr or self.email_to
		msg['Subject'] = str(Header(title, 'utf-8'))

		# 解析 SMTP 配置（允许外部覆盖）
		domain = self.email_user.split('@')[1]
		smtp_server = self.smtp_host or f'smtp.{domain}'
		# 端口优先级：显式 -> 根据是否 SSL -> 默认 465
		default_ssl_port = 465
		default_starttls_port = 587
		use_ssl = True if (self.email_use_ssl or '').lower() in ['1', 'true', 'yes'] else False
		port = None
		if self.smtp_port and self.smtp_port.isdigit():
			port = int(self.smtp_port)
		else:
			port = default_ssl_port if use_ssl else default_starttls_port

		# 优先尝试 SMTPS(SSL) 465，然后回退到 STARTTLS 587
		ssl_context = ssl.create_default_context()
		# 避免某些旧服务器的握手问题
		ssl_context.check_hostname = True
		ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
		last_error: Exception | None = None
		tried = []
		# 方案1：SMTPS 465
		try:
			if port == default_ssl_port or (use_ssl and port not in [default_ssl_port, default_starttls_port]):
				tried.append(f'SMTPS {smtp_server}:{port}')
				server = smtplib.SMTP_SSL(smtp_server, port, context=ssl_context, timeout=self.smtp_timeout)
				try:
					if self.smtp_debug:
						server.set_debuglevel(1)
					server.login(self.email_user, self.email_pass)
					server.sendmail(self.email_user, [self.email_to], msg.as_string())
					# 发送成功后，尽量优雅关闭；若关闭阶段出错，不影响结果
					try:
						server.quit()
					except Exception:
						server.close()
					return
				except Exception as e:
					last_error = e
					try:
						server.close()
					except Exception:
						pass
		except Exception as e:
			last_error = e

		# 方案2：STARTTLS 587（或显式指定）
		try:
			starttls_port = port if port != default_ssl_port else default_starttls_port
			tried.append(f'STARTTLS {smtp_server}:{starttls_port}')
			server = smtplib.SMTP(smtp_server, starttls_port, timeout=self.smtp_timeout)
			try:
				if self.smtp_debug:
					server.set_debuglevel(1)
				server.ehlo()
				server.starttls(context=ssl_context)
				server.ehlo()
				server.login(self.email_user, self.email_pass)
				server.sendmail(self.email_user, [self.email_to], msg.as_string())
				try:
					server.quit()
				except Exception:
					server.close()
				return
			except Exception as e:
				last_error = e
				try:
					server.close()
				except Exception:
					pass
		except Exception as e:
			last_error = e

		raise RuntimeError(
			f'SMTP send failed. Tried: {"; ".join(tried)}. '
			f'Please verify SMTP_HOST/SMTP_PORT/EMAIL_USE_SSL and your email provider SMTP auth (for QQ/163 use app-specific authorization code). '
			f'Last error: {last_error}'
		)

	def send_pushplus(self, title: str, content: str):
		if not self.pushplus_token:
			raise ValueError('PushPlus Token not configured')

		data = {'token': self.pushplus_token, 'title': title, 'content': content, 'template': 'html'}
		with httpx.Client(timeout=30.0) as client:
			client.post('http://www.pushplus.plus/send', json=data)

	def send_serverPush(self, title: str, content: str):
		if not self.server_push_key:
			raise ValueError('Server Push key not configured')

		data = {'title': title, 'desp': content}
		with httpx.Client(timeout=30.0) as client:
			client.post(f'https://sctapi.ftqq.com/{self.server_push_key}.send', json=data)

	def send_dingtalk(self, title: str, content: str):
		if not self.dingding_webhook:
			raise ValueError('DingTalk Webhook not configured')

		data = {'msgtype': 'text', 'text': {'content': f'{title}\n{content}'}}
		with httpx.Client(timeout=30.0) as client:
			client.post(self.dingding_webhook, json=data)

	def send_feishu(self, title: str, content: str):
		if not self.feishu_webhook:
			raise ValueError('Feishu Webhook not configured')

		data = {
			'msg_type': 'interactive',
			'card': {
				'elements': [{'tag': 'markdown', 'content': content, 'text_align': 'left'}],
				'header': {'template': 'blue', 'title': {'content': title, 'tag': 'plain_text'}},
			},
		}
		with httpx.Client(timeout=30.0) as client:
			client.post(self.feishu_webhook, json=data)

	def send_wecom(self, title: str, content: str):
		if not self.weixin_webhook:
			raise ValueError('WeChat Work Webhook not configured')

		data = {'msgtype': 'text', 'text': {'content': f'{title}\n{content}'}}
		with httpx.Client(timeout=30.0) as client:
			client.post(self.weixin_webhook, json=data)

	def send_ntfy(self,title: str, content: str):
		with httpx.Client(timeout=30.0) as client:
			client.post(self.ntfy_server, data=f'{title}\n{content}'.encode(encoding='utf-8'))

	def push_message(self, title: str, content: str, msg_type: Literal['text', 'html'] = 'text'):
		notifications = [
			('Email', lambda: self.send_email(title, content, msg_type)),
			('PushPlus', lambda: self.send_pushplus(title, content)),
			('Server Push', lambda: self.send_serverPush(title, content)),
			('DingTalk', lambda: self.send_dingtalk(title, content)),
			('Feishu', lambda: self.send_feishu(title, content)),
			('WeChat Work', lambda: self.send_wecom(title, content)),
			('Ntfy', lambda: self.send_ntfy(title, content)),
		]

		for name, func in notifications:
			try:
				func()
				print(f'[{name}]: Message push successful!')
			except Exception as e:
				print(f'[{name}]: Message push failed! Reason: {str(e)}')


notify = NotificationKit()
