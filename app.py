import re
import atexit
from datetime import date
from flask import Flask, render_template, request, redirect, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from models import db, Player, Game, DoublesGame, DoublesTeam, Ringerl, Season, SeasonSnapshot, update_elo

# Flask-App initialisieren
app = Flask(__name__)

app.secret_key = "supersecret"

# Datenbank konfigurieren (lokale SQLite-Datei)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///elo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Datenbanktabellen erzeugen (falls nicht vorhanden)
with app.app_context():
    db.create_all()

# ─── INACTIVITY SYSTEM ────────────────────────────────────

def run_daily_counter():
    """Beim App-Start: Counter +1 für alle die heute noch kein Match gespielt haben."""
    with app.app_context():
        today = date.today()
        players = Player.query.all()
        for p in players:
            last = p.last_active_date
            # Nur hochzählen wenn heute noch kein Match gespielt wurde
            if last is None or last < today:
                p.inactive_counter = (p.inactive_counter or 0) + 1
                if p.inactive_counter >= 7:
                    p.is_inactive = True
        db.session.commit()

def run_shutdown_decay():
    """Beim App-Shutdown: Inactive Spieler verlieren 5 Elo (min. 275)."""
    with app.app_context():
        players = Player.query.filter_by(is_inactive=True).all()
        for p in players:
            if p.elo > 275:
                p.elo = max(275, p.elo - 5)
        db.session.commit()

# Beim Start Counter erhöhen
run_daily_counter()

# Beim Beenden Decay ausführen
atexit.register(run_shutdown_decay)

# ─── ROUTEN ───────────────────────────────────────────────

# Startseite
@app.route('/')
def index():
    # Nur aktive Spieler im Leaderboard
    players = Player.query.filter_by(is_inactive=False).order_by(Player.elo.desc()).all()
    if players:
        players[0].rank_name = players[0].get_rank(top1=True)
        for p in players[1:]:
            p.rank_name = p.get_rank()
    last_season = Season.query.order_by(Season.number.desc()).first()
    return render_template('index.html', players=players, last_season=last_season)

# Inactive Spieler
@app.route('/inactive')
def inactive_players():
    players = Player.query.filter_by(is_inactive=True).order_by(Player.elo.desc()).all()
    for p in players:
        p.rank_name = p.get_rank()
    return render_template('inactive.html', players=players)

# Spieler hinzufügen
@app.route('/add_player', methods=['POST'])
def add_player():
    import re
    name = request.form['name'].strip()
    custom_elo = request.form.get("elo", "").strip()
    admin_pw = request.form.get("admin_password", "").strip()

    if not re.match(r'^[A-Za-z0-9äöüÄÖÜß\s]+$', name):
        flash("UNGÜLTIGER NAME: Nur Buchstaben, Zahlen und Leerzeichen erlaubt")
        return redirect('/')

    from sqlalchemy import func
    existing = Player.query.filter(func.lower(Player.name) == name.lower()).first()
    if existing:
        flash("SPIELER EXISTIERT BEREITS!")
        return redirect('/')

    elo_value = 300
    if custom_elo:
        try:
            elo_value = float(custom_elo)
        except ValueError:
            flash("UNGUELTIGER ELO-WERT!")
            return redirect("/")
        if elo_value < 100 or elo_value > 9999:
            flash("Elo muss zwischen 100 und 9999 liegen!")
            return redirect("/")
        ADMIN_PASSWORD = "123yarak"
        if admin_pw != ADMIN_PASSWORD:
            flash("FALSCHES PASSWORT! Spieler NICHT erstellt.")
            return redirect("/")

    new_player = Player(name=name, elo=elo_value, last_active_date=date.today())
    db.session.add(new_player)
    db.session.commit()
    flash(f"✅ Spieler '{name}' wurde hinzugefügt")
    return redirect('/')

# Spiel eintragen
@app.route("/add_game", methods=["POST"])
def add_game():
    p1_name = request.form["p1_name"].strip()
    p2_name = request.form["p2_name"].strip()
    series_type = int(request.form.get("series_type", 1))

    p1 = Player.query.filter(func.lower(Player.name) == p1_name.lower()).first()
    p2 = Player.query.filter(func.lower(Player.name) == p2_name.lower()).first()

    if not p1 or not p2:
        flash("Einer der Spieler wurde nicht gefunden.", "error")
        return redirect(url_for("index"))
    if p1.id == p2.id:
        flash("Ein Spieler kann nicht gegen sich selbst spielen.", "error")
        return redirect(url_for("index"))

    if series_type == 1:
        p1_score = int(request.form["p1_score"])
        p2_score = int(request.form["p2_score"])
        series_p1_wins = series_p2_wins = None

        if p1_score == p2_score:
            flash("Unentschieden sind nicht erlaubt.", "error")
            return redirect(url_for("index"))

        if max(p1_score, p2_score) < 11:
            flash("Ungültiges Ergebnis: Der Gewinner braucht mindestens 11 Punkte.", "error")
            return redirect(url_for("index"))

        if p1_score > p2_score:
            winner, loser = p1, p2
            winner_score, loser_score = p1_score, p2_score
        else:
            winner, loser = p2, p1
            winner_score, loser_score = p2_score, p1_score

        win_change, lose_change, bonus, winstreak = update_elo(
            winner, loser, winner_score, loser_score, series_type=1
        )
    else:
        needed = (series_type // 2) + 1
        p1_wins = int(request.form["p1_wins"])
        p2_wins = int(request.form["p2_wins"])

        if p1_wins == p2_wins:
            flash("Unentschieden sind nicht erlaubt.", "error")
            return redirect(url_for("index"))
        if max(p1_wins, p2_wins) != needed:
            flash(f"Ungültiges Ergebnis für Best of {series_type} (Sieger braucht {needed} Wins).", "error")
            return redirect(url_for("index"))

        p1_score = p2_score = None
        series_p1_wins, series_p2_wins = p1_wins, p2_wins

        if p1_wins > p2_wins:
            winner, loser = p1, p2
            sw, lw = p1_wins, p2_wins
        else:
            winner, loser = p2, p1
            sw, lw = p2_wins, p1_wins

        win_change, lose_change, bonus, winstreak = update_elo(
            winner, loser,
            series_type=series_type,
            series_winner_wins=sw,
            series_loser_wins=lw
        )
        p1_score = p1_wins
        p2_score = p2_wins

    game = Game(
        p1_id=p1.id, p2_id=p2.id,
        p1_score=p1_score, p2_score=p2_score,
        p1_change=win_change if winner == p1 else lose_change,
        p2_change=lose_change if winner == p1 else win_change,
        p1_elo_after=p1.elo, p2_elo_after=p2.elo,
        series_type=series_type,
        series_p1_wins=series_p1_wins,
        series_p2_wins=series_p2_wins,
    )
    db.session.add(game)
    db.session.commit()

    series_label = f"Best of {series_type}" if series_type > 1 else "Single Game"
    bonus_text = f" (+{bonus} Bonus 🔥)" if bonus > 0 else ""
    if lose_change >= 0:
        loser_text = f"{loser.name} gewinnt {lose_change} Elo 🎖️"
    else:
        loser_text = f"{loser.name} verliert {abs(lose_change)} Elo"

    flash(f"[{series_label}] {winner.name} gewinnt! +{win_change}{bonus_text} | {loser_text}", "success")
    return redirect(url_for("index"))

# Letztes Spiel rückgängig machen
@app.route('/revert_game', methods=['POST'])
def revert_game():
    last_game = Game.query.order_by(Game.id.desc()).first()
    if not last_game:
        flash("Kein Spiel zum Rückgängigmachen gefunden.", "error")
        return redirect(url_for("index"))

    p1 = db.session.get(Player, last_game.p1_id)
    p2 = db.session.get(Player, last_game.p2_id)

    p1.elo = last_game.p1_elo_after - last_game.p1_change
    p2.elo = last_game.p2_elo_after - last_game.p2_change

    db.session.delete(last_game)
    db.session.commit()

    flash(f"↩️ Letztes Spiel ({p1.name} vs {p2.name}) wurde rückgängig gemacht.", "success")
    return redirect(url_for("index"))

# Season Reset
@app.route('/season_reset', methods=['POST'])
def season_reset():
    ADMIN_PASSWORD = "123yarak"
    entered_pw = request.form.get("admin_password", "").strip()
    if entered_pw != ADMIN_PASSWORD:
        flash("Falsches Admin-Passwort – Reset abgebrochen.", "error")
        return redirect(url_for("index"))

    last_season = Season.query.order_by(Season.number.desc()).first()
    season_number = (last_season.number + 1) if last_season else 1

    new_season = Season(number=season_number)
    db.session.add(new_season)
    db.session.flush()

    players = Player.query.order_by(Player.elo.desc()).all()
    for i, p in enumerate(players):
        rank = p.get_rank(top1=(i == 0))
        snapshot = SeasonSnapshot(
            season_id=new_season.id,
            player_name=p.name,
            final_elo=p.elo,
            rank_name=rank
        )
        db.session.add(snapshot)

    def get_start_elo(old_elo):
        if old_elo >= 700:
            return 500
        elif old_elo >= 600:
            return 450
        elif old_elo >= 500:
            return 400
        elif old_elo >= 400:
            return 350
        else:
            return 300

    for p in players:
        p.elo = get_start_elo(p.elo)
        p.winstreak_1 = 0
        p.winstreak_3 = 0
        p.winstreak_5 = 0
        p.winstreak_7 = 0
        p.placements_played = 0
        p.inactive_counter = 0
        p.is_inactive = False
        p.last_active_date = date.today()

    Game.query.delete()
    Ringerl.query.delete()
    DoublesGame.query.delete()
    DoublesTeam.query.delete()

    db.session.commit()
    flash(f"✅ Season {season_number} wurde gestartet! Alle Spieler sind in Placement (3 Spiele).", "success")
    return redirect(url_for("index"))

# Season History
@app.route('/season/<int:season_number>')
def season_history(season_number):
    season = Season.query.filter_by(number=season_number).first_or_404()
    snapshots = SeasonSnapshot.query.filter_by(season_id=season.id).order_by(SeasonSnapshot.final_elo.desc()).all()
    all_seasons = Season.query.order_by(Season.number.desc()).all()
    return render_template('season_history.html', season=season, snapshots=snapshots, all_seasons=all_seasons)

# Head to Head
@app.route('/h2h', methods=['GET', 'POST'])
def h2h():
    result = None
    p1_name = p2_name = ""

    if request.method == 'POST':
        p1_name = request.form['p1_name'].strip()
        p2_name = request.form['p2_name'].strip()

        p1 = Player.query.filter(func.lower(Player.name) == p1_name.lower()).first()
        p2 = Player.query.filter(func.lower(Player.name) == p2_name.lower()).first()

        if not p1 or not p2:
            flash("Einer der Spieler wurde nicht gefunden.", "error")
        elif p1.id == p2.id:
            flash("Bitte zwei verschiedene Spieler eingeben.", "error")
        else:
            games = Game.query.filter(
                ((Game.p1_id == p1.id) & (Game.p2_id == p2.id)) |
                ((Game.p1_id == p2.id) & (Game.p2_id == p1.id))
            ).order_by(Game.id.desc()).all()

            p1_wins = sum(
                1 for g in games if
                (g.p1_id == p1.id and g.p1_score > g.p2_score) or
                (g.p2_id == p1.id and g.p2_score > g.p1_score)
            )
            p2_wins = len(games) - p1_wins

            result = {
                'p1': p1, 'p2': p2,
                'p1_wins': p1_wins, 'p2_wins': p2_wins,
                'games': games, 'total': len(games)
            }

    players = Player.query.order_by(Player.name).all()
    return render_template('h2h.html', result=result, players=players,
                           p1_name=p1_name, p2_name=p2_name)

# Vollständiges Leaderboard
@app.route('/leaderboard')
def leaderboard():
    players = Player.query.filter_by(is_inactive=False).order_by(Player.elo.desc()).all()
    if players:
        players[0].rank_name = players[0].get_rank(top1=True)
        for p in players[1:]:
            p.rank_name = p.get_rank()
    return render_template('leaderboard.html', players=players)

@app.route("/edit_player/<int:player_id>", methods=["GET", "POST"])
def edit_player(player_id):
    ADMIN_PASSWORD = "123yarak"
    player = Player.query.get_or_404(player_id)

    if request.method == "POST":
        entered_pw = request.form.get("admin_password", "").strip()
        if entered_pw != ADMIN_PASSWORD:
            flash("🚫 Falsches Admin-Passwort – Änderung abgebrochen!")
            return redirect("/")

        new_name = request.form.get("name", "").strip()
        if not new_name:
            flash("⚠️ Name darf nicht leer sein!")
            return redirect("/")

        try:
            new_elo = float(request.form.get("elo", player.elo))
        except ValueError:
            flash("⚠️ Ungültiger Elo-Wert!")
            return redirect("/")

        if new_elo < 100 or new_elo > 9999:
            flash("⚠️ Elo muss zwischen 100 und 9999 liegen!")
            return redirect("/")

        player.name = new_name
        player.elo = new_elo
        db.session.commit()
        flash(f"✅ Spieler '{player.name}' wurde erfolgreich aktualisiert (Elo: {new_elo})")
        return redirect("/")

    return render_template("edit_player.html", player=player)

@app.route("/delete_player/<int:player_id>", methods=["POST"])
def delete_player(player_id):
    ADMIN_PASSWORD = "123yarak"
    player = Player.query.get_or_404(player_id)

    if request.method == "POST":
        entered_pw = request.form.get("admin_password", "").strip()
        if entered_pw != ADMIN_PASSWORD:
            flash("🚫 Falsches Admin-Passwort – Spieler wurde NICHT gelöscht.")
            return redirect(f"/edit_player/{player_id}")

    db.session.delete(player)
    db.session.commit()
    flash(f"🗑️ Spieler '{player.name}' wurde gelöscht.")
    return redirect("/")

@app.route('/history')
def history():
    games = Game.query.order_by(Game.id.desc()).limit(20).all()
    ringerls = Ringerl.query.order_by(Ringerl.id.desc()).limit(20).all()
    players = {p.id: p.name for p in Player.query.all()}
    return render_template("history.html", games=games, ringerls=ringerls, players=players)

@app.route("/player/<int:player_id>")
def player_profile(player_id):
    player = Player.query.get_or_404(player_id)

    all_games = Game.query.filter(
        (Game.p1_id == player.id) | (Game.p2_id == player.id)
    ).order_by(Game.id.desc()).all()

    total_wins = total_losses = 0
    for g in all_games:
        if (g.p1_id == player.id and g.p1_score > g.p2_score) or \
           (g.p2_id == player.id and g.p2_score > g.p1_score):
            total_wins += 1
        else:
            total_losses += 1

    total_games = total_wins + total_losses
    winrate = round((total_wins / total_games * 100), 1) if total_games > 0 else 0
    games = all_games[:20]

    top1 = player.elo == db.session.query(db.func.max(Player.elo)).scalar()
    rank = player.get_rank(top1=top1)
    players = {p.id: p.name for p in Player.query.all()}

    return render_template(
        "player.html",
        player=player,
        games=games,
        players=players,
        wins=total_wins,
        losses=total_losses,
        total_games=total_games,
        winrate=winrate,
        rank=rank,
    )

# Ringerl
@app.route('/add_ringerl', methods=['POST'])
def add_ringerl():
    name = request.form['name'].strip()
    player = Player.query.filter(func.lower(Player.name) == name.lower()).first()

    if not player:
        flash("Spieler nicht gefunden.", "error")
        return redirect(url_for('index'))

    player.elo = min(9999, player.elo + 10)
    ringerl = Ringerl(winner_id=player.id, elo_change=10, elo_after=player.elo)
    db.session.add(ringerl)
    db.session.commit()

    flash(f"🏅 {player.name} hat ein Ringerl gewonnen! +10 Elo", "success")
    return redirect(url_for('index'))

# ─── DOPPEL ───────────────────────────────────────────────

@app.route('/doubles')
def doubles_index():
    teams = DoublesTeam.query.order_by(DoublesTeam.elo.desc()).all()
    if teams:
        teams[0].rank_name = teams[0].get_rank(top1=True)
        for t in teams[1:]:
            t.rank_name = t.get_rank()
    else:
        for t in teams:
            t.rank_name = t.get_rank()
    return render_template('doubles_index.html', teams=teams)

@app.route('/doubles/add_team', methods=['POST'])
def doubles_add_team():
    name = request.form['name'].strip()
    custom_elo = request.form.get("elo", "").strip()
    admin_pw = request.form.get("admin_password", "").strip()

    if not re.match(r'^[A-Za-z0-9äöüÄÖÜß\s&\-]+$', name):
        flash("UNGÜLTIGER NAME!", "error")
        return redirect('/doubles')

    existing = DoublesTeam.query.filter(func.lower(DoublesTeam.name) == name.lower()).first()
    if existing:
        flash("TEAM EXISTIERT BEREITS!", "error")
        return redirect('/doubles')

    elo_value = 300
    if custom_elo:
        try:
            elo_value = float(custom_elo)
        except ValueError:
            flash("UNGÜLTIGER ELO-WERT!", "error")
            return redirect('/doubles')
        if elo_value < 100 or elo_value > 9999:
            flash("Elo muss zwischen 100 und 9999 liegen!", "error")
            return redirect('/doubles')
        if admin_pw != "123yarak":
            flash("FALSCHES PASSWORT!", "error")
            return redirect('/doubles')

    db.session.add(DoublesTeam(name=name, elo=elo_value))
    db.session.commit()
    flash(f"✅ Team '{name}' wurde hinzugefügt", "success")
    return redirect('/doubles')

@app.route('/doubles/add_game', methods=['POST'])
def doubles_add_game():
    t1_name = request.form["t1_name"].strip()
    t2_name = request.form["t2_name"].strip()
    series_type = int(request.form.get("series_type", 1))

    t1 = DoublesTeam.query.filter(func.lower(DoublesTeam.name) == t1_name.lower()).first()
    t2 = DoublesTeam.query.filter(func.lower(DoublesTeam.name) == t2_name.lower()).first()

    if not t1 or not t2:
        flash("Eines der Teams wurde nicht gefunden.", "error")
        return redirect('/doubles')
    if t1.id == t2.id:
        flash("Ein Team kann nicht gegen sich selbst spielen.", "error")
        return redirect('/doubles')

    if series_type == 1:
        t1_score = int(request.form["t1_score"])
        t2_score = int(request.form["t2_score"])
        if t1_score == t2_score:
            flash("Unentschieden sind nicht erlaubt.", "error")
            return redirect('/doubles')
        if max(t1_score, t2_score) < 11:
            flash("Ungültiges Ergebnis: Der Gewinner braucht mindestens 11 Punkte.", "error")
            return redirect('/doubles')
        winner, loser = (t1, t2) if t1_score > t2_score else (t2, t1)
        ws, ls = (t1_score, t2_score) if t1_score > t2_score else (t2_score, t1_score)
        win_change, lose_change, bonus, winstreak = update_elo(winner, loser, ws, ls, series_type=1)
        series_t1_wins = series_t2_wins = None
    else:
        needed = (series_type // 2) + 1
        t1_wins = int(request.form["t1_wins"])
        t2_wins = int(request.form["t2_wins"])
        if t1_wins == t2_wins or max(t1_wins, t2_wins) != needed:
            flash(f"Ungültiges Ergebnis für Best of {series_type}.", "error")
            return redirect('/doubles')
        winner, loser = (t1, t2) if t1_wins > t2_wins else (t2, t1)
        sw, lw = (t1_wins, t2_wins) if t1_wins > t2_wins else (t2_wins, t1_wins)
        win_change, lose_change, bonus, winstreak = update_elo(
            winner, loser, series_type=series_type, series_winner_wins=sw, series_loser_wins=lw)
        t1_score, t2_score = t1_wins, t2_wins
        series_t1_wins, series_t2_wins = t1_wins, t2_wins

    game = DoublesGame(
        t1_id=t1.id, t2_id=t2.id,
        t1_score=t1_score, t2_score=t2_score,
        t1_change=win_change if winner == t1 else lose_change,
        t2_change=lose_change if winner == t1 else win_change,
        t1_elo_after=t1.elo, t2_elo_after=t2.elo,
        series_type=series_type,
        series_t1_wins=series_t1_wins,
        series_t2_wins=series_t2_wins,
    )
    db.session.add(game)
    db.session.commit()

    label = f"Best of {series_type}" if series_type > 1 else "Single"
    bonus_text = f" (+{bonus} Bonus 🔥)" if bonus > 0 else ""
    flash(f"[{label}] {winner.name} gewinnt! +{win_change}{bonus_text} | {loser.name} verliert {abs(lose_change)} Elo", "success")
    return redirect('/doubles')

@app.route('/doubles/leaderboard')
def doubles_leaderboard():
    teams = DoublesTeam.query.order_by(DoublesTeam.elo.desc()).all()
    if teams:
        teams[0].rank_name = teams[0].get_rank(top1=True)
        for t in teams[1:]:
            t.rank_name = t.get_rank()
    return render_template('doubles_leaderboard.html', teams=teams)

@app.route('/doubles/history')
def doubles_history():
    games = DoublesGame.query.order_by(DoublesGame.id.desc()).limit(20).all()
    teams = {t.id: t.name for t in DoublesTeam.query.all()}
    return render_template('doubles_history.html', games=games, teams=teams)

@app.route('/doubles/team/<int:team_id>')
def doubles_team_profile(team_id):
    team = DoublesTeam.query.get_or_404(team_id)
    games = DoublesGame.query.filter(
        (DoublesGame.t1_id == team.id) | (DoublesGame.t2_id == team.id)
    ).order_by(DoublesGame.id.desc()).limit(20).all()

    wins = losses = 0
    for g in games:
        if (g.t1_id == team.id and g.t1_score > g.t2_score) or \
           (g.t2_id == team.id and g.t2_score > g.t1_score):
            wins += 1
        else:
            losses += 1

    total = wins + losses
    winrate = round(wins / total * 100, 1) if total > 0 else 0
    top1 = team.elo == db.session.query(db.func.max(DoublesTeam.elo)).scalar()
    rank = team.get_rank(top1=top1)
    teams = {t.id: t.name for t in DoublesTeam.query.all()}

    return render_template('doubles_team.html', team=team, games=games,
                           teams=teams, wins=wins, losses=losses,
                           winrate=winrate, rank=rank)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)