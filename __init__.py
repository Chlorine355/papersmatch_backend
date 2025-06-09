import os
s2key = os.environ["S2_API_KEY"]
bot_token = os.environ['BOT_TOKEN']
import traceback
import ast
from random import choice, randint
from math import ceil
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from PapersMatch.get_related import get_related_papers, GraphVisualization, get_related_batch, get_batch_papers
import requests
from concurrent.futures import ThreadPoolExecutor
# import time
from PapersMatch.data import db_session
from PapersMatch.data.graphs import Graph
from PapersMatch.data.users import User, Ip
from PapersMatch.data.forms import LoginForm, RegisterForm
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_required, login_user, current_user, logout_user
import uuid
import datetime
from dateutil.relativedelta import relativedelta
from bs4 import BeautifulSoup as bs
import json
import telepot


app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
app.config['SECRET_KEY'] = os.environ["PM_SECRET_KEY"]

login_manager = LoginManager(app)
login_manager.login_view = 'login'

bot = telepot.Bot(bot_token)

db_session.global_init("/var/www/PapersMatch/PapersMatch/db/graphs.db")
session = db_session.create_session()


@app.route('/robots.txt')
@app.route('/sitemap.xml')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])


@app.route("/")
def search_empty():
    utm = request.args.get("utm") if request.args.get("utm") else None
    if utm:
        with open("/var/www/PapersMatch/PapersMatch/utmlog.txt", "a", encoding='utf-8') as myfile:
            myfile.write(utm + '\n')
    return render_template("search-empty.html", title="PapersMatch", searchbar=False, hint=choice(['COVID-19', 'Noam Chomsky','Metaphors We Live by', 'Swedish Empire', 'Cats', 'Гарри Поттер', 'Статистика рака', 'Вакцинация в Африке', 'Открытая наука', 'прохождение нейтрино через вещество', 'лесные пожары']))


@app.route("/<query>/<int:page>")
def search(query, page):
    year_from, year_to = request.args.get("from") if request.args.get("from") else "", request.args.get("to") if request.args.get("to") else ""
    year_range = "year=" + year_from + "-" + year_to if year_from or year_to else ""
    min_c = request.args.get("min_citations") if request.args.get("min_citations") else ""
    min_citations = "minCitationCount=" + request.args.get("min_citations") if request.args.get("min_citations") else ""
    isopenaccess = "openAccessPdf" if request.args.get("isopenaccess") else ""
    try:
        query = query.strip()
        r = requests.get(f"https://api.semanticscholar.org/graph/v1/paper/search?query={query}&offset={(page-1)*20}&limit=20"
                         f"&fields=title,authors,year,fieldsOfStudy,abstract,citationCount,tldr,isOpenAccess,openAccessPdf&{year_range}&{min_citations}&{isopenaccess}", headers={'x-api-key': s2key})
        results = r.json()['data'] if r.json() and r.json()['total'] else []
        '''
        try:
            cl_r = requests.post("https://cyberleninka.ru/api/search",
                             data=json.dumps({"mode": "articles", "q": query, "size": 20, "from": (page - 1) * 20, "year_from": int(year_from) if year_from else 0, "year_to": int(year_to) if year_to else 9999}),
                             )
            cl_r = json.loads(cl_r.content.decode())['articles']
            for article in cl_r:
                results.insert(randint(0, len(results)),
                {'abstract': bs(article['annotation'], 'html.parser').text,
                 'title': bs(article["name"], "html.parser").text,
                 'paperId': "cl:" + article['link'].replace('/', '_'),
                 'year': article["year"],
                 'authors': [{'name': x} for x in article['authors']] if article['authors'] else []})
        except Exception as e:
            print(e)
	'''
        total_pages = min(ceil(r.json()['total'] / 20), 50)
        pages_array = []
        if total_pages < 6:
            pages_array = [x for x in range(1, total_pages + 1)]
        elif page < 4:
            pages_array = [1, 2, 3, 4, 5]
        elif page + 2 >= total_pages:
            pages_array = [total_pages - 4, total_pages - 3, total_pages - 2, total_pages - 1, total_pages]
        else:
            pages_array = [page - 2, page - 1, page, page + 1, page + 2]


        return render_template("search.html", results=results, query=query, pages_array=pages_array, total_pages=total_pages,
                               title=query + " | PapersMatch", searchbar=False, count=len(results), page=page, year_from=year_from, year_to=year_to, min_citations=min_c, isopenaccess=isopenaccess, debug_info="")
    except Exception as e:
        print(e)
        print(r.json())


@app.route('/graph/<paper_id>')
def graph(paper_id):
    tries_used = 0
    with session.no_autoflush:
        if not current_user.is_authenticated: # or current_user.subscription_ends is None or current_user.subscription_ends < datetime.datetime.today().date():
            if request.environ.get('HTTP_X_FORWARDED_FOR') is None:
                ip = request.environ['REMOTE_ADDR']
            else:
                ip = request.environ['HTTP_X_FORWARDED_FOR']
            visits = session.query(Ip).filter(Ip.ip == ip).first()
            if not visits: # пришел впервые
                new_ip = Ip(ip=ip, visits=1)
                session.add(new_ip)
                session.commit()
                tries_used = 1
            else:
                if visits.visits == 5: # пришёл третьи
                    flash("Лимит для гостей: 5 графов в месяц", 'info')
                    flash("Оформите подписку, чтобы просмотреть больше графов", 'info')
                    return redirect(url_for('login', return_to=paper_id))
                else:
                    visits.visits += 1
                    tries_used = visits.visits
                    session.commit()



    from_db = session.query(Graph).filter(Graph.paperId == paper_id).first()
    if not from_db:
        G = GraphVisualization()
        if not paper_id.startswith("cl:"):
            origin, related_to_root_list = get_related_papers(paper_id)
            print(origin['externalIds'])
            id_to_paper = {paper_id: origin}
            G.addNode(paper_id)
            G.origin = paper_id
            related_to_root_list = [rel for rel in related_to_root_list if rel['paperId']]
            for rel in related_to_root_list:
                id_to_paper[rel['paperId']] = rel  # save
                G.addEdge(paper_id, rel["paperId"])
            related_to_root_ids = [rel['paperId'] for rel in related_to_root_list]
            newrels = get_related_batch(related_to_root_ids)
            for i in range(len(newrels)):
                if newrels[i].get("citations"):
                    for citation in newrels[i]['citations']:
                        if citation['paperId']:
                            id_to_paper[citation['paperId']] = citation
                            G.addEdge(related_to_root_ids[i], citation['paperId'])
                if newrels[i].get("references"):
                    for reference in newrels[i].get('references', []):
                        if reference['paperId']:
                            id_to_paper[reference['paperId']] = reference
                            G.addEdge(related_to_root_ids[i], reference['paperId']) 
            gr = G.get_graph()
            node_list = list(gr.nodes)
            all_keys = list(id_to_paper.keys())
            for key in all_keys:
                if key not in node_list:
                    del id_to_paper[key]
            papers = get_batch_papers(list(id_to_paper.keys()))
        else:
            r = requests.get("https://cyberleninka.ru" + paper_id[3:].replace("_", "/"))
            soup = bs(r.content, 'html.parser')
            '''with open("/var/www/PapersMatch/PapersMatch/searches.txt", "a", encoding='utf-8') as myfile:
                myfile.write(r.content.decode())'''

            origin = {'title': soup.find("i").get_text(),
                      'paperId': paper_id,
                      'citationCount': 0,
                      'abstract': soup.find("p", {"itemprop": "description"}).get_text() if soup.find("p", {"itemprop": "description"}) else '',
                      'year': int(soup.find("time", {"itemprop": "datePublished"}).get_text()) if soup.find("time", {"itemprop": "datePublished"}) else ''}
            id_to_paper = {paper_id: origin}
            G.addNode(paper_id)
            similars = soup.findAll("a", class_="similar")
            for similar in similars:
                sim = {'title': similar.find("div", class_="title").get_text(),
                      'paperId': "cl:" + similar["href"].replace("/", "_"),
                      'citationCount': 0,
                      'year': int(similar.find("span").get_text().split("/")[0].strip()),
                       }
                G.addEdge(paper_id, "cl:" + similar["href"].replace("/", "_"))
                id_to_paper["cl:" + similar["href"].replace("/", "_")] = sim
            gr = G.get_graph()
            node_list = list(gr.nodes)
        years = sorted([article['year'] for article in papers if article['year'] is not None])
        new_gr = Graph(paperId=paper_id, articles=str(list(papers)), edges=str(gr.edges), origin=str(origin),
                   year1=years[0] if years else None, year2=years[-1] if years else None)
        session.add(new_gr)
        session.commit()
        return render_template('graph.html', articles=papers, edges=gr.edges, origin=origin,
                               minyear=years[0] if years else None, maxyear=years[-1] if years else None, title="Граф для " + origin['title'], searchbar=True, tries_used=tries_used, debug=str(origin))
    else:
        origin = ast.literal_eval(from_db.origin)
        return render_template('graph.html', articles=ast.literal_eval(from_db.articles), edges=ast.literal_eval(from_db.edges), origin=origin,
                               minyear=from_db.year1, maxyear=from_db.year2, title="Граф для " + origin['title'], searchbar=True, tries_used=tries_used, debug=str(origin))


@app.errorhandler(500)
def server_error(e):
    bot.sendMessage(1108408903, traceback.format_exc())
    return render_template('error.html', status_code='500', message='Попробуйте перезагрузить страницу или подождать.')


@app.errorhandler(404)
def server_error_404(e):
    return render_template('error.html', status_code='404', message='Страница не найдена!')


@login_manager.user_loader
def load_user(user_id):
    return session.query(User).get(user_id)


@app.route('/profile')
@login_required
def profile():
    if not current_user.futureOrderId:
        new_uuid = uuid.uuid4().hex
        current_user.futureOrderId = new_uuid
        session.commit()
    return render_template("profile.html", title='Профиль', orderId=current_user.futureOrderId, debug="")

@app.route('/login/', methods=['post', 'get'])
def login():
    if current_user.is_authenticated:
	    return redirect(url_for('profile'))
    form = LoginForm()
    if form.validate_on_submit():
    	user = session.query(User).filter(User.email == form.email.data).first()
    	if user and user.check_password(form.password.data):
    	    login_user(user, remember=form.remember.data)
    	    if request.args.get('return_to'):
    	        return redirect(url_for('graph', paper_id=request.args.get('return_to')))
    	    else:
    	        return redirect(url_for('search_empty'))

    	flash("Неверный логин или пароль!", 'error')
    	if request.args.get('return_to'):
    	    return redirect(url_for('login', return_to=request.args.get('return_to')))
    	else:
    	    return redirect(url_for('login'))
    return render_template('login.html', form=form, title='Вход', return_to=request.args.get('return_to'))

@app.route('/register', methods=['post', 'get'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        user = session.query(User).filter(User.email == form.email.data).first()
        if user:
            flash("Пользователь с такой почтой уже существует.", 'error')
            if request.args.get('return_to'):
                return redirect(url_for('register'), return_to=request.args.get('return_to'))
            else:
                return redirect(url_for('register'))
        user = User(email=form.email.data, password_hash=generate_password_hash(form.password.data), verified=False, subscription_ends=None)
        session.add(user)
        session.commit()
        if request.args.get('return_to'):
            return redirect(url_for('login', return_to=request.args.get('return_to')))
        else:
            return redirect(url_for('login'))
    return render_template('register.html', form=form, title='Регистрация', return_to=request.args.get('return_to'))

@app.route('/logout/')
@login_required
def logout():
    logout_user()
    flash("Вы вышли из аккаунта")
    return redirect(url_for('login'))



@app.route('/paymentResult', methods=['POST'])
def paymentresult():
    response = request.json
    if response["Success"] and response["Status"] == "CONFIRMED":
        user = session.query(User).filter(User.futureOrderId == response["OrderId"]).first()
        user.futureOrderId = uuid.uuid4().hex
        if user.subscription_ends is None or user.subscription_ends < datetime.datetime.today().date():
            user.subscription_ends = datetime.datetime.today() + relativedelta(months=1)
        else:
            user.subscription_ends = user.subscription_ends + relativedelta(months=1)
        session.commit()
    with open("/var/www/PapersMatch/PapersMatch/payresults.txt", "a", encoding='utf-8') as myfile:
        myfile.write(str(request.json) + '\n')
    return "200 OK"


@app.route('/saves')
def saved():
    return render_template("saved.html")


@app.route('/proof_of_authorship')
def proooof():
    return "Сайт написан Андреем Акимовым и будет представлен как выпускная квалификационная работа"
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
