-- Run this in your Supabase SQL Editor to enable atomic scoring
create or replace function update_score(
  p_username text,
  p_points int,
  p_won boolean
)
returns void as
$$
begin
  insert into leaderboard (username, points, correct_guesses, total_games)
  values (p_username, p_points, case when p_won then 1 else 0 end, 1)
  on conflict (username) do update
  set points = leaderboard.points + p_points,
      correct_guesses = leaderboard.correct_guesses + (case when p_won then 1 else 0 end),
      total_games = leaderboard.total_games + 1;
end;
$$
language plpgsql;