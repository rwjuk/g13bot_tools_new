
# -*- coding: utf-8 -*-
"""
Scripts to manage categories.

Syntax: python g13_nudge_bot.py [-from:UNDERSCORED_CATEGORY]
"""

#
# (C) Rob W.W. Hooft, 2004
# (C) Daniel Herding, 2004
# (C) Wikipedian, 2004-2008
# (C) leogregianin, 2004-2008
# (C) Cyde, 2006-2010
# (C) Anreas J Schwab, 2007
# (C) xqt, 2009-2012
# (C) Pywikipedia team, 2008-2012
# (C) Hasteur, 2013
#
__version__ = '$Id$'
#
# Distributed under the terms of the MIT license.
#

import os, re, pickle, bz2, time, datetime, sys, logging
from dateutil.relativedelta import relativedelta
import pywikibot

from pywikibot import i18n, Bot, config, pagegenerators
#DB CONFIG
from db_handle import *
import pdb

afc_notify_list = []

# This is required for the text that is shown when you run this script
# with the parameter -help.
docuReplacements = {
    '&params;': pagegenerators.parameterHelp
}

def nudge_drive(category_name):
    logger = logging.getLogger('g13_nudge_bot')
    page_text = pywikibot.Page(pywikibot.getSite(),
            'User:HasteurBot/G13 OptIn Notifications').get()
    afc_notify_list = re.findall('\#\[\[User\:(?P<name>.*)\]\]',page_text)
    page_match = re.compile('Wikipedia talk:Articles for creation/')
    page_match2 = re.compile('Draft:')
    ip_regexp = re.compile(r'^(?:(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
                           r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)|'
                           r'(((?=(?=(.*?(::)))\3(?!.+\4)))\4?|[\dA-F]{1,4}:)'
                           r'([\dA-F]{1,4}(\4|:\b)|\2){5}'
                           r'(([\dA-F]{1,4}(\4|:\b|$)|\2){2}|'
                           r'(((2[0-4]|1\d|[1-9])?\d|25[0-5])\.?\b){4}))\Z',
                           re.IGNORECASE)
    six_months_ago = ( 
      datetime.datetime.now() + relativedelta(months=-5) 
    ).timetuple()
    logger.debug('Opened DB conn')
    #Take this out once the full authorization has been given for this bot
    potential_article = False
    interested_insert = "INSERT INTO interested_notify (article,notified) VALUES (%s, %s)"
    nom_cat = pywikibot.Category(
        pywikibot.getSite(),
        'Category:%s' % category_name
    )
    potential_articles = set(nom_cat.articles(recurse = True))
    for article in potential_articles:
        if None != page_match.match(article.title()) or \
           None != page_match2.match(article.title()) :
          pywikibot.output(article.title())
          edit_time = time.strptime( \
            article.getLatestEditors()[0]['timestamp'],
            "%Y-%m-%dT%H:%M:%SZ"
          )
          potential_article = True
          creator = article.getCreator()[0]
          if edit_time < six_months_ago:
            #Notify Creator
            #Check for already nagged
            cur = conn.cursor()
            sql_string = "SELECT COUNT(*) FROM g13_records where " + \
              "article = %s" + \
              " and editor = %s;"
            try:
              cur.execute(sql_string, (article.title(), creator))
            except:
              logger.critical("Problem with %s" % article.title())
              continue
            results = cur.fetchone()
            cur = None
            if results[0] > 0:
              #We already have notified this user
              logger.info(u"Already notifified (%s,%s)" %(creator, article.title()))
              continue
            #Perform a null edit to get the creative Category juices flowing
            logger.info('Starting to process %s' % article.title())
            article.put(newtext = article.get(), comment="Null Edit", force=True)
            logger.debug('Null Edit complete')
            user_talk_page_title = "User talk:%s" % creator
            user_talk_page = pywikibot.Page(
              pywikibot.getSite(),
              user_talk_page_title
            )
            summary = '(BOT) Notification of '+\
              'potential [[WP:G13|CSD G13]] nomination of [[%s]]' % (article.title())
            notice = "{{subst:User:Bot0612/G13_nudge_notice|{}|ip={}}} ~~~~".format(article.title(), "true" if ip_regexp.match(creator) else "")
            try:
                user_talk_text = user_talk_page.get() +"\n"+ notice
            except:
                user_talk_text = notice
            user_talk_page.put(newtext = user_talk_text,
                comment = summary,
                force=True)
            logger.debug('User Notified')
            cur = conn.cursor()
            sql_string = "INSERT INTO g13_records (article,editor)" + \
              "VALUES (%s, %s)" 
            cur.execute(sql_string, (article.title(),creator))
            conn.commit()
            logger.debug('DB stored')
            cur = None
            #Notify Interested parties
            #Get List of Editors to the page
            editor_list = []
            for rev in article.getVersionHistory():
                editor_list.append(rev[2])
            #Now let's intersect these to see who we get to notify
            intersection = set(editor_list) & set(afc_notify_list)
            message = '\n==G13 eligibility==\n[[%s]] has become eligible for G13. ~~~~' % article.title()
            while intersection:
                editor = intersection.pop()
                cur = conn.cursor()
                cur.execute(interested_insert, (article.title(),editor))
                conn.commit()
            #Take this out when finished
    if False == potential_article:
        log_page = pywikibot.Page(
            pywikibot.getSite(),
            'User:Bot0612/G13 notices'
        )
        msg = "%s no longer has potential nominations\n\n" % category_name
        page_text = log_page.get() + msg
        log_page.put(newtext = page_text,comment="Date empty")
        logger.critical(msg)
    conn.close()


def main(*args):
    global catDB
    logger = logging.getLogger('g13_nudge_bot')
    logger.setLevel(logging.DEBUG)
    trfh = logging.handlers.TimedRotatingFileHandler('logs/g13_nudge', \
        when='D', \
        interval = 3, \
        backupCount = 90, \
    )
    trfh.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    trfh.setFormatter(formatter)
    logger.addHandler(trfh)
    trfh.doRollover()

    fromGiven = False
    toGiven = False
    batchMode = False
    editSummary = ''
    inPlace = False
    overwrite = False
    showImages = False
    talkPages = False
    recurse = False
    withHistory = False
    titleRegex = None
    pagesonly = False


    # If this is set to true then the custom edit summary given for removing
    # categories from articles will also be used as the deletion reason.
    useSummaryForDeletion = True
    action = None
    sort_by_last_name = False
    restore = False
    create_pages = False
    action = 'listify'
    for arg in pywikibot.handleArgs(*args):
        if arg.startswith('-from:'):
            oldCatTitle = arg[len('-from:'):].replace('_', ' ')
            fromGiven = True
    nudge_drive(oldCatTitle)



if __name__ == "__main__":
    main()
