import os
import asyncio
import discord
import json
import markovify
import praw
import requests
import traceback
import logging
import pytz
from datetime import time, datetime
from discord import NotFound, Embed
from discord.ext import commands, tasks
from beautifultable import BeautifulTable
from lxml import etree, html

from . import utils
from .models import session, Stock, StockMessage

dirname = os.path.dirname(__file__)

json_file = open(dirname + '/model.json', 'r')

model_json = json.loads(json_file.read())

model = markovify.Text.from_json(model_json)

reddit = praw.Reddit(client_id=os.getenv('REDDIT_CLIENT_ID'),
                     client_secret=os.getenv('REDDIT_TOKEN'),
                     username=os.getenv('REDDIT_USER'),
                     password=os.getenv('REDDIT_PASS'),
                     user_agent="'<reddit-discord> accessAPI:v0.0.1 (by /u/<magu1La>)")

bot = commands.Bot(command_prefix='>')

@bot.command()
async def random(ctx, arg):
    '''Get a random post from a given subreddit.'''
    try:
        post = reddit.subreddit(arg).random()
        if 'v.redd.it' in post.url:
            post.url = post.media['reddit_video']['fallback_url']
        if 'redgifs' in post.url:
            result = requests.get(post.url)
            root = html.fromstring(result.text)
            tree = etree.ElementTree(root)
            link_id = tree.xpath('/html/head/meta[23]/@content')[0].split('/')[-1]
            post.url = 'https://thcf6.redgifs.com/' + link_id + '.webm'
        await ctx.send(post.url)
    except Exception as e:
        await ctx.send('Cai da borda e não consegui achar o que você pediu!')

@bot.command()
async def bozo(ctx):
    '''Generate a 280 char text from Bolsonaro\'s tweets.'''
    await ctx.send(model.make_short_sentence(280))

@bot.command()
async def dic(ctx, *, word):
    ''''Returns the meaning of a word using google dictionary api'''
    dict_resp = requests.get('https://api.dictionaryapi.dev/api/v1/entries/pt-BR/'+requests.utils.quote(word))
    if dict_resp.status_code == 404:
        await ctx.send('Palavra não encontrada')

    dict_resp = dict_resp.json()
    meaning = str()
    for i, j in dict_resp[0]['meaning'].items():
        meaning +=f'**{i.capitalize()}**\n'
        for x in range(0, len(j)):
            meaning +=f'\t*{x+1}*. {j[x]["definition"]}\n'

    await ctx.send(meaning)

@bot.command()
async def rito(ctx, *, summoner):
    '''Searchs for a live match in the RIOT API.'''
    riot_url = 'https://br1.api.riotgames.com'
    summoner_api = f'/lol/summoner/v4/summoners/by-name/{summoner}'
    headers={'X-Riot-Token':os.getenv('RIOT_TOKEN')}

    summoner_resp = requests.get(riot_url+summoner_api, headers=headers)

    if summoner_resp.status_code == 404:
        await ctx.send('''```
                       Invocador não encontrado!```''')

    summoner_resp = summoner_resp.json()

    account_id = summoner_resp['id']
    spec_api=f'/lol/spectator/v4/active-games/by-summoner/{account_id}'

    spec_resp = requests.get(riot_url+spec_api, headers=headers)

    if spec_resp.status_code == 404:
        await ctx.send('''```\nPartida não encontrada!```''')
    spec_resp = spec_resp.json()
    players = spec_resp['participants']
    elos = list()
    queue_type = 'RANKED_SOLO_5x5'

    if  'gameQueueConfigId' in spec_resp and spec_resp['gameQueueConfigId'] == 440:
        queue_type = 'RANKED_FLEX_SR'

    for player in players:
        ranked_stats = f'/lol/league/v4/entries/by-summoner/{player["summonerId"]}'
        resp = requests.get(riot_url+ranked_stats, headers=headers).json()
        has_elo = False

        for i in resp:
            if i['queueType'] == queue_type:
                has_elo = True
                elos.append(f'{i["tier"]} {i["rank"]}')
                break

        if not has_elo:
            elos.append('UNRANKED')

    t = BeautifulTable()
    t.set_style(BeautifulTable.STYLE_NONE)
    t.append_row([elos[0], players[0]['summonerName'], 'x', players[5]['summonerName'], elos[5]])
    t.append_row([elos[1], players[1]['summonerName'], 'x', players[6]['summonerName'], elos[6]])
    t.append_row([elos[2], players[2]['summonerName'], 'x', players[7]['summonerName'], elos[7]])
    t.append_row([elos[3], players[3]['summonerName'], 'x', players[8]['summonerName'], elos[8]])
    t.append_row([elos[4], players[4]['summonerName'], 'x', players[9]['summonerName'], elos[9]])

    await ctx.send(f'''```\n{t}```''')


@bot.command()
@commands.has_role('B3')
async def b3(ctx, op, ticket):
    '''Search for a STOCK in BOVESPA.'''
    if op == 'check':
        yahoo = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticket}.SA?region=US&'\
            'lang=en-US&includePrePost=false&interval=2m&range=1d&corsDomain=finance.yahoo.com&.tsrc=finance'
        result = requests.get(yahoo).json()

        stock = result['chart']['result'][0]['meta']
        await ctx.send(f"R${stock['regularMarketPrice']}")

    if op == 'add':
        session.add(Stock(id=ticket.upper()))
        session.commit()
        await ctx.send(f"{ticket} adicionado a lista de ações.")

    elif op == 'remove':
        session.query(Stock).filter_by(id=ticket).delete()
        await ctx.send(f"{ticket} removido da lista de ações.")
        session.commit()

@tasks.loop(minutes=5)
async def check_b3():
    if utils.is_time_between(time(10,0), time(18,0)) and datetime.today().weekday() < 5:

        stocks = session.query(Stock).all()
        message = session.query(StockMessage).first()

        channel = bot.get_channel(768224643236233226)

        embed = Embed(title="ATUALIZAÇÃO B3", description="Valor atualizado em tempo real das ações na B3", color=0x004fe0)
        embed.set_footer(text=datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y, %H:%M:%S"))

        for stock in stocks:
            yahoo = f'https://query1.finance.yahoo.com/v8/finance/chart/{stock.id}.SA?region=US&'\
            'lang=en-US&includePrePost=false&interval=1m&range=1d&corsDomain=finance.yahoo.com&.tsrc=finance'

            result = requests.get(yahoo).json()

            data = result['chart']['result'][0]['meta']

            price = data['regularMarketPrice']
            emoji = str()

            if stock.last_price is None:
                stock.last_price = price

            if price > stock.last_price:
                emoji = ':chart_with_upwards_trend:'
            elif price < stock.last_price:
                emoji = ':chart_with_downwards_trend:'
            else:
                emoji = '<:OMEGALU:766781445036965898>'

            stock.last_price = price
            embed.add_field(name=stock.id, value=f"R${price} - {emoji} ({((price / data['previousClose']) * 100 - 100):.2f}%)", inline=False)

            session.commit()

        if message:
            m = await channel.fetch_message(message.id)
            await m.edit(embed=embed)
        else:
            m = await channel.send(embed=embed)
            session.add(StockMessage(id=m.id))
            session.commit()




@bot.event
async def on_ready():
    check_b3.start()

bot.run(os.getenv('DISCORD_TOKEN'))
