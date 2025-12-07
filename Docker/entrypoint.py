import os
import sys
import logging
from time import sleep
from porkbun_ddns import PorkbunDDNS
from porkbun_ddns.config import Config, DEFAULT_ENDPOINT
from porkbun_ddns.errors import PorkbunDDNS_Error
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


logger = logging.getLogger('porkbun_ddns')
if os.getenv('DEBUG', 'False').lower() in ('true', '1', 't'):
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)
logger.propagate = False
logFormatter = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")
consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)

# Collect SMTP info
smtp_server = os.getenv('SMTP_SERVER', "smtp-relay.gmail.com")
smtp_port = int(os.getenv('SMTP_PORT', 587))
smtp_subject = os.getenv('SMTP_SUBJECT', "DNS Records updated")
smtp_username = os.getenv('SMTP_USERNAME')
smtp_password = os.getenv('SMTP_PASSWORD')
sender_email = os.getenv('SENDER_EMAIL')
receiver_emails = []
if os.getenv('RECEIVER_EMAILS', None):
    receiver_emails = [x.strip() for x in os.getenv('RECEIVER_EMAILS', None).split(',')]
enable_email = False
if smtp_server and smtp_port and smtp_username and smtp_password and sender_email and receiver_emails:
    enable_email = True

sleep_time = int(os.getenv('SLEEP', 300))
domain = os.getenv('DOMAIN', None)

if os.getenv('IPV4_ONLY', None) or os.getenv('IPV6_ONLY', None):
    raise PorkbunDDNS_Error('IPV4_ONLY and IPV6_ONLY are DEPRECATED and have been removed since v1.1.0')

public_ips = None
if os.getenv('PUBLIC_IPS', None):
    public_ips = [x.strip() for x in os.getenv('PUBLIC_IPS', None).split(',')]
fritzbox = os.getenv('FRITZBOX', None)

config = Config(DEFAULT_ENDPOINT, os.getenv('APIKEY'), os.getenv('SECRETAPIKEY'))

ipv4 = ipv6 = False
if os.getenv('IPV4', 'True').lower() in ('true', '1', 't'):
    ipv4 = True
if os.getenv('IPV6', 'False').lower() in ('true', '1', 't'):
    ipv6 = True
    
if not all([os.getenv('DOMAIN'), os.getenv('SECRETAPIKEY'), os.getenv('APIKEY')]):
    logger.info('Please set DOMAIN, SECRETAPIKEY and APIKEY')
    sys.exit(1)

if not any([ipv4, ipv6]):
    logger.info('No Protocol selected! Please set IPV4 and/or IPV6 TRUE')
    sys.exit(1)

porkbun_ddns = PorkbunDDNS(config, domain, public_ips=public_ips,
                           fritzbox_ip=fritzbox, ipv4=ipv4, ipv6=ipv6)

def GetIPsFromRecords(records):
    ret = {}
    for r in records:
        if r['name'] == porkbun_ddns.fqdn:
          key = f"{r['type']} {r['name']}"
          ret[key] = r['content']
    return ret

# Looks at before and after and returns an array of text strings describing any changes.
def FindUpdatedRecords(before, after):
    ret = []
    for k, v in before.items():
        if k in after and after[k] != v:
            ret.append(f"Record {k} changed from {v} to {after[k]}")
    for k, v in after.items():
        if k not in before:
            ret.append(f"Record {k} added with value {v}")
    for k, v in before.items():
        if k not in after:
            ret.append(f"Record {k} with value {v} removed")
    return ret

# Update the records for a subdomain and return a list of text strings
# describing any changes
def UpdateRecords(subdomain):
  if subdomain:
      porkbun_ddns.set_subdomain(subdomain)
  before = GetIPsFromRecords(porkbun_ddns.get_records())
  porkbun_ddns.update_records()
  after = GetIPsFromRecords(porkbun_ddns.get_records())
  return FindUpdatedRecords(before, after)

while True:
    changes = []
    subdomains = os.getenv('SUBDOMAINS', '')
    if subdomains:
        for subdomain in subdomains.replace(' ', '').split(','):
            changes.extend(UpdateRecords(subdomain))
    else:
        changes.extend(UpdateRecords(None))

    if changes:
      logger.info(f"Changes: {'\n'.join(changes)}")
      if enable_email:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = ', '.join(receiver_emails)
        msg['Subject'] = smtp_subject
        body = "\n".join(changes)
        msg.attach(MIMEText(body, 'plain'))
        text = msg.as_string()
        logger.info("Sending email...")
        logger.info(text)
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(sender_email, receiver_emails, text)

    logger.info('Sleeping... {}s'.format(sleep_time))
    sleep(sleep_time)
