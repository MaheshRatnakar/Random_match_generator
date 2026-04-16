import io
import random
from collections import Counter
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

import streamlit as st


Player = str
Team = Tuple[Player, Player]
Match = Tuple[Team, Team]


def parse_players(raw_text: str, count: Optional[int]) -> List[Player]:
    players = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if count is not None and count > 0:
        players = players[:count]
    return players


def is_disjoint(team_a: Team, team_b: Team) -> bool:
    return len(set(team_a).intersection(set(team_b))) == 0


def team_usage_score(team: Team, player_partner_counter: Dict[Player, Counter]) -> int:
    a, b = team
    return player_partner_counter[a][b] + player_partner_counter[b][a]


def matchup_usage_score(
    team_a: Team,
    team_b: Team,
    matchup_counter: Counter,
) -> int:
    key = tuple(sorted([tuple(sorted(team_a)), tuple(sorted(team_b))]))
    return matchup_counter[key]


def generate_all_possible_matches(players: Sequence[Player]) -> List[Match]:
    teams = list(combinations(players, 2))
    matches: List[Match] = []
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            if is_disjoint(teams[i], teams[j]):
                matches.append((teams[i], teams[j]))
    return matches


def make_schedule(
    players: Sequence[Player],
    seed: Optional[int] = None,
    consecutive_target: int = 2,
) -> List[Match]:
    if len(players) < 4:
        return []

    rng = random.Random(seed)
    all_matches = generate_all_possible_matches(players)
    rng.shuffle(all_matches)

    # Number of matches needed so every player appears near equally.
    target_matches = max(1, len(players) // 2)
    target_appearances = target_matches * 2

    player_match_count = Counter({p: 0 for p in players})
    player_streak = Counter({p: 0 for p in players})
    player_partner_counter: Dict[Player, Counter] = {p: Counter() for p in players}
    matchup_counter = Counter()

    schedule: List[Match] = []
    remaining = all_matches[:]

    while remaining:
        # Stop when all players have reached near target appearances.
        if all(player_match_count[p] >= target_appearances for p in players):
            break

        best_idx = None
        best_score = None

        for idx, (team_a, team_b) in enumerate(remaining):
            match_players = set(team_a + team_b)

            # Soft rule: prefer players who have played fewer matches so far.
            fairness_penalty = sum(player_match_count[p] for p in match_players)

            # Soft rule: avoid repeating same partners too much.
            partner_penalty = team_usage_score(team_a, player_partner_counter) + team_usage_score(
                team_b, player_partner_counter
            )

            # Soft rule: avoid repeated exact same matchup.
            rematch_penalty = matchup_usage_score(team_a, team_b, matchup_counter) * 3

            # Soft rule: try to let players get short streaks (2 consecutive) when possible.
            streak_bonus = 0
            for p in match_players:
                if player_streak[p] == 1 and consecutive_target >= 2:
                    streak_bonus -= 1
                elif player_streak[p] >= consecutive_target:
                    streak_bonus += 2

            score = fairness_penalty + partner_penalty + rematch_penalty + streak_bonus

            if best_score is None or score < best_score:
                best_score = score
                best_idx = idx

        if best_idx is None:
            break

        team_a, team_b = remaining.pop(best_idx)
        match_players = set(team_a + team_b)

        # Update streaks and counts.
        for p in players:
            if p in match_players:
                player_match_count[p] += 1
                player_streak[p] += 1
            else:
                player_streak[p] = 0

        a1, a2 = team_a
        b1, b2 = team_b
        player_partner_counter[a1][a2] += 1
        player_partner_counter[a2][a1] += 1
        player_partner_counter[b1][b2] += 1
        player_partner_counter[b2][b1] += 1

        matchup_key = tuple(sorted([tuple(sorted(team_a)), tuple(sorted(team_b))]))
        matchup_counter[matchup_key] += 1

        schedule.append((team_a, team_b))

    return schedule


def format_schedule_csv(schedule: Sequence[Match]) -> str:
    output = io.StringIO()
    output.write("Match,Team A,Team B\n")
    for idx, (team_a, team_b) in enumerate(schedule, start=1):
        output.write(
            f'{idx},"{team_a[0]} & {team_a[1]}","{team_b[0]} & {team_b[1]}"\n'
        )
    return output.getvalue()


def main() -> None:
    st.set_page_config(page_title="Badminton Doubles Scheduler", page_icon="🏸")
    st.title("🏸 Badminton Doubles Scheduler")
    st.caption("Generate fair doubles matches with rotating teams.")

    with st.sidebar:
        st.subheader("Settings")
        player_count = st.number_input(
            "Number of players",
            min_value=4,
            max_value=50,
            value=8,
            step=1,
        )
        random_seed_text = st.text_input("Random seed (optional)", value="")
        if random_seed_text.strip():
            try:
                seed = int(random_seed_text.strip())
            except ValueError:
                seed = None
                st.warning("Seed must be a number. Using random behavior.")
        else:
            seed = None

    count = int(player_count)
    if "player_names" not in st.session_state:
        st.session_state.player_names = [f"Player {i + 1}" for i in range(count)]

    # Keep the names list exactly equal to selected player count.
    current_names = st.session_state.player_names
    if len(current_names) < count:
        current_names.extend(
            [f"Player {i + 1}" for i in range(len(current_names), count)]
        )
    elif len(current_names) > count:
        current_names = current_names[:count]
    st.session_state.player_names = current_names

    st.subheader("Player Names")
    st.caption("Enter exactly one name per player.")
    cols = st.columns(2)
    entered_names: List[str] = []
    for i in range(count):
        col = cols[i % 2]
        with col:
            entered_name = st.text_input(
                f"Player {i + 1}",
                value=st.session_state.player_names[i],
                key=f"player_name_{i}",
            ).strip()
            entered_names.append(entered_name)
    st.session_state.player_names = entered_names

    if st.button("Generate Schedule", type="primary"):
        players = entered_names

        if any(not name for name in players):
            st.error("Please enter all player names before generating schedule.")
            return
        if len(set(players)) != len(players):
            st.error("Player names must be unique.")
            return
        if len(players) < 4:
            st.error("Need at least 4 players.")
            return
        if len(players) % 2 != 0:
            st.warning(
                "Odd number of players detected. One player may sit out in each round."
            )

        schedule = make_schedule(players, seed=seed, consecutive_target=2)

        if not schedule:
            st.error("Could not generate schedule. Try different players or seed.")
            return

        st.success(f"Created {len(schedule)} matches.")
        for i, (team_a, team_b) in enumerate(schedule, start=1):
            st.write(
                f"**Match {i}:** "
                f"`{team_a[0]} & {team_a[1]}`  vs  `{team_b[0]} & {team_b[1]}`"
            )

        csv_data = format_schedule_csv(schedule)
        st.download_button(
            "Download as CSV",
            data=csv_data,
            file_name="badminton_schedule.csv",
            mime="text/csv",
        )

        appearances = Counter()
        for team_a, team_b in schedule:
            for p in team_a + team_b:
                appearances[p] += 1

        st.subheader("Fairness View")
        st.write("Matches played per player:")
        st.json(dict(sorted(appearances.items(), key=lambda item: str(item[0]))))


if __name__ == "__main__":
    main()
