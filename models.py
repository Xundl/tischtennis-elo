from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    elo = db.Column(db.Float, default=300)
    winstreak = db.Column(db.Integer, default=0)

    def get_rank(self, top1=False):
        if top1:
            return "Karl Jindraks Doppelpartner"
        
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
                divisions = 3
                step = (high - low) / divisions
                if elo < low + step:
                    div = 3
                elif elo < low + 2 * step:
                    div = 2
                else:
                    div = 1
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
    series_type = db.Column(db.Integer, default=1)       # 1, 3, 5 oder 7
    series_p1_wins = db.Column(db.Integer, default=None) # z.B. 2 bei BO3
    series_p2_wins = db.Column(db.Integer, default=None) # z.B. 1 bei BO3

def update_elo(winner, loser, winner_score=None, loser_score=None,
               series_type=1, series_winner_wins=None, series_loser_wins=None, k=32):
    
    expected_win = 1 / (1 + 10 ** ((loser.elo - winner.elo) / 400))

    if series_type == 1 and winner_score is not None and loser_score is not None:
        diff = abs(winner_score - loser_score)
        diff_factor = 1 + (min(diff, 10) / 20)
    else:
        diff_factor = 1.0

    series_multipliers = {1: 1.0, 3: 1.3, 5: 1.6, 7: 2.0}
    series_mult = series_multipliers.get(series_type, 1.0)

    # Basis-Delta (ohne Boni) → wird für den Verlierer verwendet
    base_delta = int(round(k * (1 - expected_win) * diff_factor * series_mult))

    # Boni NUR für den Gewinner
    sweep_bonus = 0
    if series_type > 1 and series_loser_wins == 0:
        sweep_bonus = {3: 5, 5: 8, 7: 12}.get(series_type, 0)

    winstreak_bonus = 5 if winner.winstreak >= 2 else 0

    total_bonus = sweep_bonus + winstreak_bonus

    # ✅ Gewinner: base + Boni
    winner.elo = min(1000, winner.elo + base_delta + total_bonus)

    # ✅ Verlierer: nur 75% vom base_delta, KEINE Boni
    loser_delta = int(round(base_delta * 0.75))
    loser.elo = max(100, loser.elo - loser_delta)

    winner.winstreak += 1
    loser.winstreak = 0

    db.session.commit()
    return base_delta + total_bonus, -loser_delta, total_bonus, winner.winstreak