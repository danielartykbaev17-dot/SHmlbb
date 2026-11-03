import os, sqlite3
from functools import wraps
from flask import Flask,g,request,redirect,url_for,session,flash,render_template,abort
from werkzeug.security import generate_password_hash,check_password_hash
app=Flask(__name__); app.secret_key=os.environ.get("SECRET_KEY","replace-this-before-publishing")
DB=os.environ.get("DATABASE_PATH","shmlbb.sqlite3")
def db():
 if "db" not in g: g.db=sqlite3.connect(DB); g.db.row_factory=sqlite3.Row; g.db.execute("PRAGMA foreign_keys=ON")
 return g.db
@app.teardown_appcontext
def close(e):
 c=g.pop("db",None)
 if c: c.close()
def init():
 c=sqlite3.connect(DB); c.executescript("""
 CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE,email TEXT UNIQUE,password_hash TEXT,game_nick TEXT DEFAULT '',game_id TEXT DEFAULT '',zone_id TEXT DEFAULT '',server TEXT DEFAULT '',rank TEXT DEFAULT 'Не указан',role TEXT DEFAULT 'Любая',bio TEXT DEFAULT '');
 CREATE TABLE IF NOT EXISTS teams(id INTEGER PRIMARY KEY,name TEXT,description TEXT,server TEXT,rank_min TEXT,rank_max TEXT,role_needed TEXT,captain_id INTEGER REFERENCES users(id));
 CREATE TABLE IF NOT EXISTS applications(id INTEGER PRIMARY KEY,team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,message TEXT,status TEXT DEFAULT 'pending',UNIQUE(team_id,user_id));
 CREATE TABLE IF NOT EXISTS seasons(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,active INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS player_season_stats(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,season_id INTEGER REFERENCES seasons(id) ON DELETE CASCADE,role TEXT NOT NULL,mvp INTEGER DEFAULT 0,wins INTEGER DEFAULT 0,matches INTEGER DEFAULT 0,UNIQUE(user_id,season_id));
 CREATE TABLE IF NOT EXISTS team_season_stats(id INTEGER PRIMARY KEY,team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,season_id INTEGER REFERENCES seasons(id) ON DELETE CASCADE,wins INTEGER DEFAULT 0,matches INTEGER DEFAULT 0,points INTEGER DEFAULT 0,UNIQUE(team_id,season_id));
 """); c.commit(); c.close()
def user(): return db().execute("SELECT * FROM users WHERE id=?",(session["uid"],)).fetchone() if session.get("uid") else None
@app.context_processor
def ctx(): return {"me":user()}
def auth(f):
 @wraps(f)
 def w(*a,**k):
  if not session.get("uid"): return redirect(url_for("login"))
  return f(*a,**k)
 return w
@app.route("/")
def home():
 return render_template("home.html",players=db().execute("SELECT * FROM users ORDER BY id DESC LIMIT 6").fetchall(),teams=db().execute("SELECT t.*,u.username captain FROM teams t JOIN users u ON u.id=t.captain_id ORDER BY t.id DESC LIMIT 4").fetchall(),pc=db().execute("SELECT COUNT(*) FROM users").fetchone()[0],tc=db().execute("SELECT COUNT(*) FROM teams").fetchone()[0])
@app.route("/register",methods=["GET","POST"])
def register():
 if request.method=="POST":
  n=request.form["username"].strip(); e=request.form["email"].strip().lower(); p=request.form["password"]
  if len(n)<3 or len(p)<8 or "@" not in e: flash("Проверь ник, email и пароль (минимум 8 символов).","error")
  else:
   try:
    cur=db().execute("INSERT INTO users(username,email,password_hash) VALUES(?,?,?)",(n,e,generate_password_hash(p))); db().commit(); session["uid"]=cur.lastrowid; return redirect("/profile")
   except sqlite3.IntegrityError: flash("Такой ник или email уже используется.","error")
 return render_template("auth.html",register=True)
@app.route("/login",methods=["GET","POST"])
def login():
 if request.method=="POST":
  x=request.form["identity"].lower(); u=db().execute("SELECT * FROM users WHERE lower(username)=? OR email=?",(x,x)).fetchone()
  if u and check_password_hash(u["password_hash"],request.form["password"]): session.clear(); session["uid"]=u["id"]; return redirect("/dashboard")
  flash("Неверный логин или пароль.","error")
 return render_template("auth.html",register=False)
@app.route("/logout")
def logout(): session.clear(); return redirect("/")
@app.route("/dashboard")
@auth
def dashboard():
 u=user(); own=db().execute("SELECT * FROM teams WHERE captain_id=?",(u["id"],)).fetchall()
 apps=db().execute("SELECT a.status,t.name FROM applications a JOIN teams t ON t.id=a.team_id WHERE a.user_id=?",(u["id"],)).fetchall()
 return render_template("dashboard.html",u=u,own=own,apps=apps)
@app.route("/profile",methods=["GET","POST"])
@auth
def profile():
 u=user()
 if request.method=="POST":
  v=[request.form.get(k,"").strip() for k in ["game_nick","game_id","zone_id","server","rank","role","bio"]]
  if (v[1] and not v[1].isdigit()) or (v[2] and not v[2].isdigit()): flash("Player ID и Zone ID должны содержать только цифры.","error")
  else:
   db().execute("UPDATE users SET game_nick=?,game_id=?,zone_id=?,server=?,rank=?,role=?,bio=? WHERE id=?",(*v,u["id"])); db().commit(); flash("Профиль сохранён.","success"); return redirect("/profile")
 return render_template("profile.html",u=u)
@app.route("/players")
def players():
 q=request.args.get("q",""); role=request.args.get("role",""); rank=request.args.get("rank",""); server=request.args.get("server","")
 sql="SELECT * FROM users WHERE 1=1"; a=[]
 if q: sql+=" AND (username LIKE ? OR game_nick LIKE ?)"; a += [f"%{q}%",f"%{q}%"]
 for col,val in [("role",role),("rank",rank)]:
  if val: sql+=f" AND {col}=?"; a.append(val)
 if server: sql+=" AND server LIKE ?"; a.append(f"%{server}%")
 return render_template("players.html",players=db().execute(sql+" ORDER BY id DESC",a).fetchall(),q=q,role=role,rank=rank,server=server)
@app.route("/teams")
def teams(): return render_template("teams.html",teams=db().execute("SELECT t.*,u.username captain FROM teams t JOIN users u ON u.id=t.captain_id ORDER BY t.id DESC").fetchall())
@app.route("/teams/create",methods=["GET","POST"])
@auth
def create():
 if request.method=="POST":
  n=request.form["name"].strip()
  if len(n)<3: flash("Название должно быть не короче 3 символов.","error")
  else:
   c=db().execute("INSERT INTO teams(name,description,server,rank_min,rank_max,role_needed,captain_id) VALUES(?,?,?,?,?,?,?)",(n,request.form.get("description",""),request.form.get("server",""),request.form.get("rank_min",""),request.form.get("rank_max",""),request.form.get("role_needed","Любая"),session["uid"])); db().commit(); return redirect(url_for("team",tid=c.lastrowid))
 return render_template("create.html")
@app.route("/teams/<int:tid>")
def team(tid):
 t=db().execute("SELECT t.*,u.username captain FROM teams t JOIN users u ON u.id=t.captain_id WHERE t.id=?",(tid,)).fetchone()
 if not t: abort(404)
 pending=db().execute("SELECT a.*,u.username FROM applications a JOIN users u ON u.id=a.user_id WHERE a.team_id=? AND a.status='pending'",(tid,)).fetchall() if session.get("uid")==t["captain_id"] else []
 applied=bool(db().execute("SELECT 1 FROM applications WHERE team_id=? AND user_id=?",(tid,session.get("uid",-1))).fetchone())
 return render_template("team.html",t=t,pending=pending,applied=applied)
@app.route("/teams/<int:tid>/apply",methods=["POST"])
@auth
def apply(tid):
 try: db().execute("INSERT INTO applications(team_id,user_id,message) VALUES(?,?,?)",(tid,session["uid"],request.form.get("message",""))); db().commit(); flash("Заявка отправлена.","success")
 except sqlite3.IntegrityError: flash("Ты уже отправлял заявку.","error")
 return redirect(url_for("team",tid=tid))
@app.route("/applications/<int:aid>/<action>",methods=["POST"])
@auth
def decide(aid,action):
 a=db().execute("SELECT a.*,t.captain_id,t.id tid FROM applications a JOIN teams t ON t.id=a.team_id WHERE a.id=?",(aid,)).fetchone()
 if not a or a["captain_id"]!=session["uid"] or action not in ("accept","reject"): abort(403)
 db().execute("UPDATE applications SET status=? WHERE id=?",("accepted" if action=="accept" else "rejected",aid)); db().commit(); return redirect(url_for("team",tid=a["tid"]))

@app.route("/leaderboard")
def leaderboard(): return render_template("leaderboard.html",players=db().execute("SELECT * FROM users ORDER BY CASE rank WHEN 'Mythical Immortal' THEN 1 WHEN 'Mythical Glory' THEN 2 WHEN 'Mythical Honor' THEN 3 WHEN 'Mythic' THEN 4 WHEN 'Legend' THEN 5 ELSE 6 END LIMIT 100").fetchall())

@app.route("/awards")
def awards():
 active=db().execute("SELECT * FROM seasons WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
 roles=["Jungler","Mid Lane","Gold Lane","EXP Lane","Roamer"]; current={}; alltime={}
 for role in roles:
  current[role]=db().execute("SELECT u.*,SUM(p.mvp) mvps,SUM(p.wins) wins FROM player_season_stats p JOIN users u ON u.id=p.user_id WHERE p.season_id=? AND p.role=? GROUP BY u.id ORDER BY mvps DESC,wins DESC LIMIT 1",(active["id"] if active else -1,role)).fetchone()
  alltime[role]=db().execute("SELECT u.*,SUM(p.mvp) mvps,SUM(p.wins) wins FROM player_season_stats p JOIN users u ON u.id=p.user_id WHERE p.role=? GROUP BY u.id ORDER BY mvps DESC,wins DESC LIMIT 1",(role,)).fetchone()
 best_season=db().execute("SELECT u.*,SUM(p.mvp) mvps,SUM(p.wins) wins FROM player_season_stats p JOIN users u ON u.id=p.user_id WHERE p.season_id=? GROUP BY u.id ORDER BY mvps DESC,wins DESC LIMIT 1",(active["id"] if active else -1,)).fetchone()
 best_all=db().execute("SELECT u.*,SUM(p.mvp) mvps,SUM(p.wins) wins FROM player_season_stats p JOIN users u ON u.id=p.user_id GROUP BY u.id ORDER BY mvps DESC,wins DESC LIMIT 1").fetchone()
 best_team=db().execute("SELECT t.*,SUM(x.wins) wins,SUM(x.points) points FROM team_season_stats x JOIN teams t ON t.id=x.team_id WHERE x.season_id=? GROUP BY t.id ORDER BY wins DESC,points DESC LIMIT 1",(active["id"] if active else -1,)).fetchone()
 all_team=db().execute("SELECT t.*,SUM(x.wins) wins,SUM(x.points) points FROM team_season_stats x JOIN teams t ON t.id=x.team_id GROUP BY t.id ORDER BY wins DESC,points DESC LIMIT 1").fetchone()
 return render_template("awards.html",active=active,roles=roles,current=current,alltime=alltime,best_season=best_season,best_all=best_all,best_team=best_team,all_team=all_team)
@app.route("/admin/awards",methods=["GET","POST"])
def awards_admin():
 key=os.environ.get("SHMLBB_ADMIN_KEY","")
 if not key or (request.values.get("admin_key","") != key and not session.get("awards_admin_ok")): return render_template("awards_admin.html",authorized=False)
 session["awards_admin_ok"]=True
 if request.method=="POST":
  action=request.form.get("action")
  try:
   if action=="season":
    name=request.form.get("season_name","").strip(); db().execute("UPDATE seasons SET active=0"); db().execute("INSERT INTO seasons(name,active) VALUES(?,1) ON CONFLICT(name) DO UPDATE SET active=1",(name,)); db().commit(); flash("Текущий сезон обновлён.","success")
   elif action=="player":
    db().execute("INSERT INTO player_season_stats(user_id,season_id,role,mvp,wins,matches) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,season_id) DO UPDATE SET role=excluded.role,mvp=excluded.mvp,wins=excluded.wins,matches=excluded.matches",(int(request.form["user_id"]),int(request.form["season_id"]),request.form["role"],int(request.form["mvp"]),int(request.form["wins"]),int(request.form["matches"]))); db().commit(); flash("Статистика игрока сохранена.","success")
   elif action=="team":
    db().execute("INSERT INTO team_season_stats(team_id,season_id,wins,matches,points) VALUES(?,?,?,?,?) ON CONFLICT(team_id,season_id) DO UPDATE SET wins=excluded.wins,matches=excluded.matches,points=excluded.points",(int(request.form["team_id"]),int(request.form["season_id"]),int(request.form["wins"]),int(request.form["matches"]),int(request.form["points"]))); db().commit(); flash("Статистика команды сохранена.","success")
  except (ValueError,KeyError): flash("Проверь введённые данные.","error")
 return render_template("awards_admin.html",authorized=True,seasons=db().execute("SELECT * FROM seasons ORDER BY id DESC").fetchall(),users=db().execute("SELECT id,username,game_nick FROM users ORDER BY username").fetchall(),teams=db().execute("SELECT id,name FROM teams ORDER BY name").fetchall())

if __name__=="__main__": init(); app.run(host="127.0.0.1",port=5000,debug=True)
