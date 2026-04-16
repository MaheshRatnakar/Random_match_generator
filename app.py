import io
import random
from collections import Counter
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Set, Tuple

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


def build_round_robin_from_teams(teams: Sequence[Team]) -> List[Match]:
    matches: List[Match] = []
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            matches.append((teams[i], teams[j]))
    return matches


def order_matches_with_consecutive_limit(
    matches: Sequence[Match],
    consecutive_limit: int = 2,
) -> List[Match]:
    if not matches:
        return []

    all_teams = set()
    for team_a, team_b in matches:
        all_teams.add(team_a)
        all_teams.add(team_b)

    ordered: List[Match] = []
    remaining = list(matches)
    streaks = {team: 0 for team in all_teams}

    while remaining:
        best_idx: Optional[int] = None
        best_score: Optional[Tuple[int, int]] = None

        for idx, (team_a, team_b) in enumerate(remaining):
            active = {team_a, team_b}
            next_streaks = {}
            violates_limit = False
            for team in all_teams:
                if team in active:
                    next_streak = streaks[team] + 1
                    if next_streak > consecutive_limit:
                        violates_limit = True
                    next_streaks[team] = next_streak
                else:
                    next_streaks[team] = 0

            if violates_limit:
                continue

            # Prefer matches that keep streaks shorter and balance appearances.
            max_streak = max(next_streaks.values())
            total_streak = sum(next_streaks.values())
            score = (max_streak, total_streak)
            if best_score is None or score < best_score:
                best_score = score
                best_idx = idx

        # If strict limit cannot be satisfied at this step, pick first remaining
        # to guarantee schedule completion.
        if best_idx is None:
            best_idx = 0

        chosen_a, chosen_b = remaining.pop(best_idx)
        chosen_active = {chosen_a, chosen_b}
        for team in all_teams:
            streaks[team] = streaks[team] + 1 if team in chosen_active else 0
        ordered.append((chosen_a, chosen_b))

    return ordered


def create_random_teams(players: Sequence[Player], rng: random.Random) -> List[Team]:
    shuffled = list(players)
    rng.shuffle(shuffled)
    teams: List[Team] = []
    for i in range(0, len(shuffled), 2):
        teams.append((shuffled[i], shuffled[i + 1]))
    return teams


def normalize_team(team: Team) -> Team:
    return tuple(sorted(team))


def generate_even_player_schedule(
    players: Sequence[Player],
    seed: Optional[int],
    team_rotations: int,
) -> List[Match]:
    rng = random.Random(seed)
    schedule: List[Match] = []
    seen_teams: Set[Team] = set()

    for _ in range(team_rotations):
        # Try multiple shuffles so new team combinations are preferred.
        best_teams: Optional[List[Team]] = None
        best_reuse_count: Optional[int] = None
        for _attempt in range(60):
            candidate = create_random_teams(players, rng)
            reuse_count = sum(
                1 for team in candidate if normalize_team(team) in seen_teams
            )
            if best_reuse_count is None or reuse_count < best_reuse_count:
                best_reuse_count = reuse_count
                best_teams = candidate
            if reuse_count == 0:
                break

        teams = best_teams if best_teams is not None else create_random_teams(players, rng)
        for team in teams:
            seen_teams.add(normalize_team(team))

        block_matches = build_round_robin_from_teams(teams)
        # Keep all pairings in the same block, while limiting long consecutive
        # runs by the same team (target: at most 2 in a row).
        ordered_block_matches = order_matches_with_consecutive_limit(
            block_matches, consecutive_limit=2
        )
        schedule.extend(ordered_block_matches)

    return schedule


def make_schedule(
    players: Sequence[Player],
    seed: Optional[int] = None,
    consecutive_target: int = 2,
    team_rotations: int = 2,
) -> List[Match]:
    if len(players) < 4:
        return []
    if len(players) % 2 == 0:
        return generate_even_player_schedule(players, seed=seed, team_rotations=team_rotations)

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
        team_rotations = st.number_input(
            "Team rotations (for even player count)",
            min_value=1,
            max_value=20,
            value=4,
            step=1,
            help=(
                "In each rotation, teams stay fixed and play all other teams once. "
                "After that, teams are reshuffled."
            ),
        )
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

        schedule = make_schedule(
            players,
            seed=seed,
            consecutive_target=2,
            team_rotations=int(team_rotations),
        )

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
