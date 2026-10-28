export function hourlyCents(survey) {
  return survey.rewardCents / survey.minutes * 60;
}

export function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function summarize(state, now = new Date()) {
  const completed = state.surveys.filter(s => s.status === 'completed');
  const today = completed.filter(s => s.completedAt && sameDay(new Date(s.completedAt), now));
  const available = state.surveys.filter(s => s.status === 'available').sort((a, b) => hourlyCents(b) - hourlyCents(a));
  const sum = items => items.reduce((total, item) => total + item.rewardCents, 0);
  const week = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6 + index);
    return { date, cents: sum(completed.filter(s => s.completedAt && sameDay(new Date(s.completedAt), date))) };
  });
  return { totalCents: sum(completed), todayCents: sum(today), completedCount: completed.length, todayCount: today.length, available, week };
}
