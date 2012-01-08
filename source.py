import os
import simplejson
import datetime
import time
import urllib2
from elementtree import ElementTree
from strings import *
import ysapi

import xbmc
import pickle
from sqlite3 import dbapi2 as sqlite3

STREAM_DR1 = 'plugin://plugin.video.dr.dk.live/?playChannel=1'
STREAM_DR2 = 'plugin://plugin.video.dr.dk.live/?playChannel=2'
STREAM_DR_UPDATE = 'plugin://plugin.video.dr.dk.live/?playChannel=3'
STREAM_DR_K = 'plugin://plugin.video.dr.dk.live/?playChannel=4'
STREAM_DR_RAMASJANG = 'plugin://plugin.video.dr.dk.live/?playChannel=5'
STREAM_DR_HD = 'plugin://plugin.video.dr.dk.live/?playChannel=6'
STREAM_24_NORDJYSKE = 'plugin://plugin.video.dr.dk.live/?playChannel=200'

class Channel(object):
    def __init__(self, id, title, logo = None, streamUrl = None):
        self.id = id
        self.title = title
        self.logo = logo
        self.streamUrl = streamUrl

    def isPlayable(self):
        return hasattr(self, 'streamUrl') and self.streamUrl

    def __repr__(self):
        return 'Channel(id=%s, title=%s, logo=%s, streamUrl=%s)' \
               % (self.id, self.title, self.logo, self.streamUrl)

class Program(object):
    def __init__(self, channel, title, startDate, endDate, description, imageLarge = None, imageSmall=None):
        """

        @param channel:
        @type channel: source.Channel
        @param title:
        @param startDate:
        @param endDate:
        @param description:
        @param imageLarge:
        @param imageSmall:
        """
        self.channel = channel
        self.title = title
        self.startDate = startDate
        self.endDate = endDate
        self.description = description
        self.imageLarge = imageLarge
        self.imageSmall = imageSmall

    def __repr__(self):
        return 'Program(channel=%s, title=%s, startDate=%s, endDate=%s, description=%s, imageLarge=%s, imageSmall=%s)' % \
            (self.channel, self.title, self.startDate, self.endDate, self.description, self.imageLarge, self.imageSmall)


class Source(object):
    KEY = "undefiend"
    STREAMS = {}
    SOURCE_DB = 'source.db'

    def __init__(self, settings, hasChannelIcons):
        self.channelIcons = hasChannelIcons
        self.cachePath = settings['cache.path']
        self.playbackUsingDanishLiveTV = settings['danishlivetv.playback'] == 'true'

        self.conn = sqlite3.connect(os.path.join(self.cachePath, self.SOURCE_DB), check_same_thread = False)
        self._createTables()

    def __del__(self):
        self.conn.close()

    def hasChannelIcons(self):
        return self.channelIcons

    def updateChannelAndProgramListCaches(self):
        print "[script.tvguide] Updating channel list caches..."
        channelList = self.getChannelList()

        for channel in channelList:
            print "[script.tvguide] Updating program list caches for channel " + channel.title.decode('iso-8859-1') + "..."
            self.getProgramList(channel)

        print "[script.tvguide] Done updating caches."

    def getChannelList(self):
        cacheFile = os.path.join(self.cachePath, self.KEY + '.channellist')

        try:
            cachedOn = datetime.datetime.fromtimestamp(os.path.getmtime(cacheFile))
            cacheHit = cachedOn.day == datetime.datetime.now().day
        except OSError:
            cacheHit = False

        channelList = None
        if not cacheHit:
            try:
                channelList = self._getChannelList()
                # Setup additional stream urls
                for channel in channelList:
                    if channel.streamUrl:
                        continue
                    elif self.playbackUsingDanishLiveTV and self.STREAMS.has_key(channel.id):
                        channel.streamUrl = self.STREAMS[channel.id]
                        
                pickle.dump(channelList, open(cacheFile, 'w'))
            except Exception, ex:
                print "[script.tvguide] Unable to get channel list\n" + str(ex)
        else:
            try:
                channelList = pickle.load(open(cacheFile))
            except Exception:
                pass

        return channelList

    def _getChannelList(self):
        return None

    def getProgramList(self, channel):
        id = str(channel.id).replace('/', '')
        cacheFile = os.path.join(self.cachePath, self.KEY + '-' + id + '.programlist')

        try:
            cachedOn = datetime.datetime.fromtimestamp(os.path.getmtime(cacheFile))
            cacheHit = cachedOn.day == datetime.datetime.now().day
        except OSError:
            cacheHit = False

        programList = None
        if not cacheHit:
            try:
                programList = self._getProgramList(channel)
                pickle.dump(programList, open(cacheFile, 'w'))
            except Exception, ex:
                print "[script.tvguide] Unable to get program list for channel: " + str(channel) + "\n" + str(ex)
        else:
            programList = pickle.load(open(cacheFile))

        return programList
    
    def _getProgramList(self, channel):
        return None

    def _downloadUrl(self, url):
        u = urllib2.urlopen(url)
        content = u.read()
        u.close()
            
        return content

    def setCustomStreamUrl(self, channel, stream_url):
        c = self.conn.cursor()
        c.execute("DELETE FROM custom_stream_url WHERE channel=?", [channel.id])
        c.execute("INSERT INTO custom_stream_url(channel, stream_url) VALUES(?, ?)", [channel.id, stream_url])
        self.conn.commit()
        c.close()

    def getCustomStreamUrl(self, channel):
        c = self.conn.cursor()
        c.execute("SELECT stream_url FROM custom_stream_url WHERE channel=?", [channel.id])
        stream_url = c.fetchone()
        c.close()

        if stream_url:
            return stream_url[0]
        else:
            return None

    def deleteCustomStreamUrl(self, channel):
        c = self.conn.cursor()
        c.execute("DELETE FROM custom_stream_url WHERE channel=?", [channel.id])
        self.conn.commit()
        c.close()

    def isPlayable(self, channel):
        customStreamUrl = self.getCustomStreamUrl(channel)
        return customStreamUrl is not None or channel.isPlayable()

    def play(self, channel):
        customStreamUrl = self.getCustomStreamUrl(channel)
        if customStreamUrl:
            print type(customStreamUrl)
            xbmc.log("Playing custom stream url: %s" % customStreamUrl)
            xbmc.Player().play(item = customStreamUrl)

        elif channel.isPlayable():
            xbmc.log("Playing : %s" % channel.streamUrl)
            xbmc.Player().play(item = channel.streamUrl)

    def _createTables(self):
        c = self.conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS custom_stream_url(channel TEXT, stream_url TEXT)")
        c.close()


class DrDkSource(Source):
    KEY = 'drdk'
    CHANNELS_URL = 'http://www.dr.dk/tjenester/programoversigt/dbservice.ashx/getChannels?type=tv'
    PROGRAMS_URL = 'http://www.dr.dk/tjenester/programoversigt/dbservice.ashx/getSchedule?channel_source_url=%s&broadcastDate=%s'

    STREAMS = {
        'dr.dk/mas/whatson/channel/DR1' : STREAM_DR1,
        'dr.dk/mas/whatson/channel/DR2' : STREAM_DR2,
        'dr.dk/external/ritzau/channel/dru' : STREAM_DR_UPDATE,
        'dr.dk/mas/whatson/channel/TVR' : STREAM_DR_RAMASJANG,
        'dr.dk/mas/whatson/channel/TVK' : STREAM_DR_K,
        'dr.dk/mas/whatson/channel/TV' : STREAM_DR_HD
    }

    def __init__(self, settings):
        Source.__init__(self, settings, False)
        self.date = datetime.datetime.today()

    def _getChannelList(self):
        jsonChannels = simplejson.loads(self._downloadUrl(self.CHANNELS_URL))
        channelList = list()

        for channel in jsonChannels['result']:
            c = Channel(id = channel['source_url'], title = channel['name'])
            channelList.append(c)

        return channelList

    def _getProgramList(self, channel):
        url = self.PROGRAMS_URL % (channel.id.replace('+', '%2b'), self.date.strftime('%Y-%m-%dT%H:%M:%S'))
        jsonPrograms = simplejson.loads(self._downloadUrl(url))
        programs = list()

        for program in jsonPrograms['result']:
            if program.has_key('ppu_description'):
                description = program['ppu_description']
            else:
                description = strings(NO_DESCRIPTION)

            programs.append(Program(channel, program['pro_title'], self._parseDate(program['pg_start']), self._parseDate(program['pg_stop']), description))

        return programs
    
    def _parseDate(self, dateString):
        t = time.strptime(dateString[:19], '%Y-%m-%dT%H:%M:%S')
        return datetime.datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)


class YouSeeTvSource(Source):
    KEY = 'youseetv'

    STREAMS = {
        1 : STREAM_DR1,
        2 : STREAM_DR2,
        889 : STREAM_DR_UPDATE,
        505: STREAM_DR_RAMASJANG,
        504 : STREAM_DR_K,
        503 : STREAM_DR_HD
    }

    def __init__(self, settings):
        Source.__init__(self, settings, True)
        self.date = datetime.datetime.today()
        self.channelCategory = settings['youseetv.category']
        self.ysApi = ysapi.YouSeeTVGuideApi()
        self.playbackUsingYouSeeWebTv = settings['youseewebtv.playback'] == 'true'

    def _getChannelList(self):
        channelList = list()
        for channel in self.ysApi.channelsInCategory(self.channelCategory):
            c = Channel(id = channel['id'], title = channel['name'], logo = channel['logo'])
            if self.playbackUsingYouSeeWebTv:
                c.streamUrl = 'plugin://plugin.video.yousee.tv/?channel=' + str(c.id)
            channelList.append(c)

        return channelList

    def _getProgramList(self, channel):
        programs = list()
        for program in self.ysApi.programs(channel.id):
            description = program['description']
            if description is None:
                description = strings(NO_DESCRIPTION)

            imagePrefix = program['imageprefix']

            p = Program(
                channel,
                program['title'],
                self._parseDate(program['begin']),
                self._parseDate(program['end']),
                description,
                imagePrefix + program['images_sixteenbynine']['large'],
                imagePrefix + program['images_sixteenbynine']['small'],
            )
            programs.append(p)

        return programs

    def _parseDate(self, dateString):
        return datetime.datetime.fromtimestamp(dateString)


class TvTidSource(Source):
    # http://tvtid.tv2.dk/js/fetch.js.php/from-1291057200.js
    KEY = 'tvtiddk'

    BASE_URL = 'http://tvtid.tv2.dk%s'
    FETCH_URL = BASE_URL % '/js/fetch.js.php/from-%d.js'

    STREAMS = {
        11825154 : STREAM_DR1,
        11823606 : STREAM_DR2,
        11841417 : STREAM_DR_UPDATE,
        25995179 : STREAM_DR_RAMASJANG,
        26000893 : STREAM_DR_K,
        26005640 : STREAM_DR_HD
    }

    def __init__(self, settings):
        Source.__init__(self, settings, True)
        self.time = time.time()

        # calculate nearest hour
        self.time -= self.time % 3600

    def _getChannelList(self):
        response = self._downloadUrl(self.FETCH_URL % self.time)
        json = simplejson.loads(response)

        channelList = list()
        for channel in json['channels']:
            print str(channel['id']) + " - " + channel['name'].encode('utf-8', 'replace')
            logoFile = self.BASE_URL % channel['logo']

            c = Channel(id = channel['id'], title = channel['name'], logo = logoFile)
            channelList.append(c)

        return channelList

    def _getProgramList(self, channel):
        response = self._downloadUrl(self.FETCH_URL % self.time)
        json = simplejson.loads(response)

        c = None
        for c in json['channels']:
            if c['id'] == channel.id:
                break

        # assume we always find a channel
        programs = list()

        for program in c['program']:
            description = program['short_description']
            if description is None:
                description = strings(NO_DESCRIPTION)

            programs.append(Program(channel, program['title'], datetime.datetime.fromtimestamp(program['start_timestamp']), datetime.datetime.fromtimestamp(program['end_timestamp']), description))

        return programs

class XMLTVSource(Source):
    KEY = 'xmltv'

    STREAMS = {
        'DR1.dr.dk' : STREAM_DR1,
        'www.ontv.dk/tv/1' : STREAM_DR1
    }

    def __init__(self, settings):
        self.xmlTvFile = settings['xmltv.file']
        self.time = time.time()
        try:
            doc = self._loadXml()
            hasChannelIcons = doc.find('channel/icon') is not None
        except Exception:
            hasChannelIcons = False

        super(XMLTVSource, self).__init__(settings, hasChannelIcons)

        # calculate nearest hour
        self.time -= self.time % 3600

    def _getChannelList(self):
        doc = self._loadXml()
        channelList = list()
        for channel in doc.findall('channel'):
            logo = None
            if channel.find('icon'):
                logo = channel.find('icon').get('src')
            c = Channel(id = channel.get('id'), title = channel.findtext('display-name'), logo = logo)
            channelList.append(c)

        return channelList

    def _getProgramList(self, channel):
        doc = self._loadXml()
        programs = list()
        for program in doc.findall('programme'):
            if program.get('channel') != channel.id:
                continue

            description = program.findtext('desc')
            if description is None:
                description = strings(NO_DESCRIPTION)

            programs.append(Program(channel, program.findtext('title'), self._parseDate(program.get('start')), self._parseDate(program.get('stop')), description))

        return programs

    def _loadXml(self):
        f = open(self.xmlTvFile)
        xml = f.read()
        f.close()

        return ElementTree.fromstring(xml)


    def _parseDate(self, dateString):
        dateStringWithoutTimeZone = dateString[:-6]
        t = time.strptime(dateStringWithoutTimeZone, '%Y%m%d%H%M%S')
        return datetime.datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)

