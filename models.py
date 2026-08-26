from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Season(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, nullable=False)
    ended_at = db.Column(db.DateTime, default=datetime.utcnow)

class SeasonSnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id'))
    player_name = db.Column(db.String(50))
    final_elo = db.Column(db.Float)
    rank_name = db.Column(db.String(100))

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    elo = db.Column(db.Float, default=300)
    winstreak_1 = db.Column(db.Integer, default=0)
    winstreak_3 = db.Column(db.Integer, default=0)
    winstreak_5 = db.Column(db.Integer, default=0)
    winstreak_7 = db.Column(db.Integer, default=0)
    placements_played = db.Column(db.Integer, default=0)

    def is_placed(self):
        return self.placements_played >= 3

    def get_rank(self, top1=False):
        if not self.is_placed():
            return "Unranked"

        # Schlager: über 1000
        if self.elo > 1000:
            if top1:
                return "Schlager 🏓 | Karl Jindraks Doppelpartner 👑"
            return "Schlager 🏓"

        if top1:
            return "Karl Jindraks Doppelpartner 👑"

        elo = max(min(self.elo, 1000), 100)
        tiers = [
            (100, 249, "Papier"),
            (250, 399, "Plastik"),
            (400, 549, "Holz"),
            (550, 699, "Metall"),
            (700, 849, "Pfarrer"),
            (850, 1000, "Familie Yarak"),
        ]
        for low, high, name in tiers:
            if low <= elo <= high:
                step = (high - low) / 3
                div = 3 if elo < low + step else (2 if elo < low + 2 * step else 1)
                return f"{name} {div}"
        return "Unranked"

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    p1_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    p2_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    p1_score = db.Column(db.Integer)
    p2_score = db.Column(db.Integer)
    p1_change = db.Column(db.Float)
    p2_change = db.Column(db.Float)
    p1_elo_after = db.Column(db.Float)
    p2_elo_after = db.Column(db.Float)
    series_type = db.Column(db.Integer, default=1)
    series_p1_wins = db.Column(db.Integer, default=None)
    series_p2_wins = db.Column(db.Integer, default=None)

def update_elo(winner, loser, winner_score=None, loser_score=None,
               series_type=1, series_winner_wins=None, series_loser_wins=None, k=32):

    # Placement: doppelter K-Wert wenn noch nicht placed
    if not winner.is_placed() or not loser.is_placed():
        k = 64

    expected_win = 1 / (1 + 10 ** ((loser.elo - winner.elo) / 400))

    if series_type == 1 and winner_score is not None and loser_score is not None:
        diff = abs(winner_score - loser_score)
        diff_factor = 1 + (min(diff, 10) / 20)
    else:
        diff_factor = 1.0

    series_multipliers = {1: 1.0, 3: 1.3, 5: 1.6, 7: 2.0}
    series_mult = series_multipliers.get(series_type, 1.0)

    base_delta = int(round(k * (1 - expected_win) * diff_factor * series_mult))

    elo_diff = abs(winner.elo - loser.elo)

    if elo_diff >= 150:
        sweep_bonus = 0
        winstreak_bonus = 0
    else:
        sweep_bonus = 0
        if series_type > 1 and series_loser_wins == 0:
            sweep_bonus = {3: 5, 5: 8, 7: 12}.get(series_type, 0)
        streak_field = f"winstreak_{series_type}"
        current_streak = getattr(winner, streak_field, 0) or 0
        winstreak_bonus = 5 if current_streak >= 2 else 0

    total_bonus = sweep_bonus + winstreak_bonus

    # Elo-Cap auf 9999 (Schlager Rang)
    winner.elo = min(9999, winner.elo + base_delta + total_bonus)
    loser_delta = int(round(base_delta * 0.75))

    underdog_bonus = 0
    if series_type > 1 and series_loser_wins is not None and series_loser_wins > 0:
        elo_tiers = int(elo_diff // 150)
        if elo_tiers >= 1:
            underdog_bonus = series_loser_wins * 2 * elo_tiers

    loser.elo = max(100, loser.elo - loser_delta + underdog_bonus)

    # Placements hochzählen
    if winner.placements_played < 3:
        winner.placements_played += 1
    if loser.placements_played < 3:
        loser.placements_played += 1

    streak_field = f"winstreak_{series_type}"
    current_streak = getattr(winner, streak_field, 0) or 0
    setattr(winner, streak_field, current_streak + 1)
    setattr(loser, streak_field, 0)

    db.session.commit()
    return base_delta + total_bonus, -loser_delta + underdog_bonus, total_bonus, getattr(winner, streak_field)

class DoublesTeam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    elo = db.Column(db.Float, default=300)
    winstreak = db.Column(db.Integer, default=0)

    def get_rank(self, top1=False):
        if top1:
            return "Karl Jindraks Doppelpartner 👑"
        elo = max(min(self.elo, 1000), 100)
        tiers = [
            (100, 249, "Papier"),
            (250, 399, "Plastik"),
            (400, 549, "Holz"),
            (550, 699, "Metall"),
            (700, 849, "Pfarrer"),
            (850, 1000, "Familie Yarak"),
        ]
        for low, high, name in tiers:
            if low <= elo <= high:
                step = (high - low) / 3
                div = 3 if elo < low + step else (2 if elo < low + 2 * step else 1)
                return f"{name} {div}"
        return "Unranked"

class DoublesGame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    t1_id = db.Column(db.Integer, db.ForeignKey('doubles_team.id'))
    t2_id = db.Column(db.Integer, db.ForeignKey('doubles_team.id'))
    t1_score = db.Column(db.Integer)
    t2_score = db.Column(db.Integer)
    t1_change = db.Column(db.Float)
    t2_change = db.Column(db.Float)
    t1_elo_after = db.Column(db.Float)
    t2_elo_after = db.Column(db.Float)
    series_type = db.Column(db.Integer, default=1)
    series_t1_wins = db.Column(db.Integer, nullable=True)
    series_t2_wins = db.Column(db.Integer, nullable=True)

class Ringerl(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    winner_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    elo_change = db.Column(db.Float, default=10)
    elo_after = db.Column(db.Float)