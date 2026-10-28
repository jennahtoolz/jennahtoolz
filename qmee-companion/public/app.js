import { hourlyCents, summarize } from './metrics.mjs';

const $ = id => document.getElementById(id);
let state;
let messages = [];
let pendingDelete;
let toastTimer;
let chatBusy = false;
const money = cents => new Intl.NumberFormat(undefined, { style: 'currency', currency: state?.currency || 'USD' }).format(cents / 100);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, { ...options, headers: { 'Content-Type': 'application/json' }, body: options.body ? JSON.stringify(options.body) : undefined });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
  return data;
}
function toast(text) {
  clearTimeout(toastTimer);
  $('toast').textContent = text;
  $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 3500);
}
function pageError(error) {
  $('page-error').textContent = error.message;
  $('page-error').hidden = false;
}
async function refresh() {
  state = await api('/state');
  render();
  $('page-error').hidden = true;
}
function render() {
  const stats = summarize(state);
  $('today-earned').textContent = money(stats.todayCents);
  $('total-earned').textContent = money(stats.totalCents);
  $('available-count').textContent = stats.available.length;
  $('today-count').textContent = `${stats.todayCount} survey${stats.todayCount === 1 ? '' : 's'} completed today`;
  $('completed-count').textContent = `${stats.completedCount} completed in total`;
  const percent = Math.round(stats.todayCents / state.dailyGoalCents * 100);
  $('goal-amount').textContent = `${money(stats.todayCents)} of ${money(state.dailyGoalCents)}`;
  $('goal-percent').textContent = `${percent}%`;
  $('goal-progress').value = Math.min(percent, 100);
  $('goal-caption').textContent = percent >= 100 ? 'You reached your goal. That’s a small win worth celebrating.' : `${money(Math.max(0, state.dailyGoalCents - stats.todayCents))} to go. One survey at a time.`;
  $('reward-currency').textContent = `(${state.currency})`;
  $('ai-status').textContent = chatBusy ? 'Thinking…' : state.aiConfigured ? 'Connected' : 'Connect AI';
  $('ai-setup').hidden = state.aiConfigured;
  $('chat-send').disabled = !state.aiConfigured || chatBusy;
  $('question-send').disabled = !state.aiConfigured || chatBusy;
  $('question-connection').textContent = state.aiConfigured ? 'Explanation appears in your answer guide →' : 'Connect AI in environment settings to get explanations.';
  $('chat-send').title = state.aiConfigured ? 'Send message' : 'Connect AI in environment settings first';
  renderSurveys();
  $('earnings-chart').replaceChildren(...stats.week.map(({ date, cents }) => {
    const maximum = Math.max(...stats.week.map(day => day.cents), state.dailyGoalCents);
    const column = el('div', 'chart-col');
    const label = el('span', 'chart-value', money(cents));
    const track = el('div', 'chart-track');
    const bar = el('div', 'chart-bar');
    // Dynamic geometry uses a DOM style property, never user-supplied CSS.
    bar.style.height = `${Math.max(2, cents / maximum * 100)}%`;
    track.append(bar);
    const day = date.toLocaleDateString(undefined, { weekday: 'short' });
    column.setAttribute('aria-label', `${date.toLocaleDateString()}: ${money(cents)}`);
    column.append(label, track, el('span', 'chart-day', day));
    return column;
  }));
}
function showAdd() {
  if (!state) return;
  $('survey-form').reset();
  $('survey-form').querySelector('.form-error').hidden = true;
  updatePreview();
  $('survey-dialog').showModal();
}
function renderSurveys() {
  const filter = $('survey-filter').value;
  const surveys = state.surveys.filter(s => filter === 'all' || s.status === filter)
    .sort((a, b) => filter === 'available' ? hourlyCents(b) - hourlyCents(a) : b.createdAt.localeCompare(a.createdAt));
  $('survey-count').textContent = surveys.length;
  if (!surveys.length) {
    const empty = el('div', 'empty-state');
    const available = filter === 'available' || filter === 'all';
    empty.append(el('span', 'empty-symbol', available ? '▤' : '◇'), el('h3', '', available ? 'Your next small win starts here' : 'No records here yet'),
      el('p', '', available ? 'Add a survey from Qmee to compare its time and reward.' : 'Update a survey’s status from the actions menu.'));
    if (available) {
      const button = el('button', 'text-button', '+ Add your first survey');
      button.type = 'button';
      button.addEventListener('click', showAdd);
      empty.append(button);
    }
    $('survey-list').replaceChildren(empty);
    return;
  }
  $('survey-list').replaceChildren(...surveys.map(survey => {
    const row = el('div', 'survey-row');
    const title = el('div');
    title.append(el('span', 'survey-name', survey.title), el('span', 'survey-meta', { available: 'On your shortlist', completed: 'Completed · reward logged', screened_out: 'Screened out · no reward' }[survey.status]));
    const reward = el('div', 'survey-reward', money(survey.rewardCents));
    reward.append(el('span', 'survey-time', `${survey.minutes} min`));
    const hourly = el('span', 'hourly-value', `${money(hourlyCents(survey))}/h`);
    const actions = el('details', 'survey-actions');
    const toggle = el('summary', '', '⋮');
    toggle.setAttribute('aria-label', `Actions for ${survey.title}`);
    const menu = el('div', 'actions-menu');
    for (const [status, text] of [['completed', 'Mark completed'], ['screened_out', 'Screened out'], ['available', 'Move to shortlist']]) {
      if (survey.status === status) continue;
      const button = el('button', '', text);
      button.type = 'button';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try { await api(`/surveys/${survey.id}`, { method: 'PATCH', body: { status } }); await refresh(); toast('Survey updated'); }
        catch (error) { pageError(error); button.disabled = false; }
      });
      menu.append(button);
    }
    const remove = el('button', 'delete-action', 'Remove record');
    remove.type = 'button';
    remove.addEventListener('click', () => {
      actions.open = false;
      pendingDelete = survey.id;
      $('delete-description').textContent = `“${survey.title}” will be removed from your log and earnings totals.`;
      $('delete-form').querySelector('.form-error').hidden = true;
      $('delete-dialog').showModal();
    });
    menu.append(remove);
    actions.append(toggle, menu);
    row.append(title, reward, hourly, actions);
    return row;
  }));
}
async function submitForm(form, work) {
  const button = form.querySelector('button[type="submit"]');
  const error = form.querySelector('.form-error');
  error.hidden = true;
  button.disabled = true;
  try { await work(); }
  catch (problem) { error.textContent = problem.message; error.hidden = false; }
  finally { button.disabled = false; }
}
function openSettings() {
  if (!state) return;
  $('currency').value = state.currency;
  $('currency').disabled = state.surveys.length > 0;
  $('daily-goal').value = (state.dailyGoalCents / 100).toFixed(2);
  $('settings-form').querySelector('.form-error').hidden = true;
  $('settings-dialog').showModal();
}
function updatePreview() {
  const reward = Number($('survey-reward').value);
  const time = Number($('survey-minutes').value);
  $('rate-preview').textContent = reward > 0 && time > 0 ? `That’s about ${money(reward * 100 / time * 60)} per hour, if completed in ${time} minutes.` : 'Add a reward and time to compare its value.';
}
function renderChat() {
  $('chat-messages').replaceChildren(...messages.map(message => {
    const node = el('div', `chat-message ${message.role}`);
    node.append(el('span', 'chat-message-label', message.role === 'user' ? 'You' : 'SurveySide'), document.createTextNode(message.content));
    return node;
  }));
  $('chat-messages').scrollTop = $('chat-messages').scrollHeight;
}

$('today-label').textContent = new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).toUpperCase();
$('add-survey').addEventListener('click', showAdd);
$('survey-filter').addEventListener('change', () => { if (state) renderSurveys(); });
$('settings-button').addEventListener('click', openSettings);
$('edit-goal').addEventListener('click', openSettings);
for (const button of document.querySelectorAll('[data-close]')) button.addEventListener('click', () => $(button.dataset.close).close());
for (const input of [$('survey-reward'), $('survey-minutes')]) input.addEventListener('input', updatePreview);
$('survey-form').addEventListener('submit', event => {
  event.preventDefault();
  submitForm(event.currentTarget, async () => {
    await api('/surveys', { method: 'POST', body: { title: $('survey-title').value.trim(), reward: Number($('survey-reward').value), minutes: Number($('survey-minutes').value) } });
    $('survey-filter').value = 'available';
    await refresh();
    $('survey-dialog').close();
    toast('Added to your shortlist');
  });
});
$('settings-form').addEventListener('submit', event => {
  event.preventDefault();
  submitForm(event.currentTarget, async () => {
    await api('/settings', { method: 'PATCH', body: { currency: $('currency').value, dailyGoal: Number($('daily-goal').value) } });
    await refresh();
    $('settings-dialog').close();
    toast('Preferences saved');
  });
});
$('delete-form').addEventListener('submit', event => {
  event.preventDefault();
  submitForm(event.currentTarget, async () => {
    await api(`/surveys/${pendingDelete}`, { method: 'DELETE' });
    await refresh();
    $('delete-dialog').close();
    toast('Record removed');
  });
});
for (const button of document.querySelectorAll('[data-prompt]')) button.addEventListener('click', () => { $('chat-input').value = button.dataset.prompt; $('chat-input').focus(); });
async function sendMessage(content) {
  if (!content || !state?.aiConfigured || chatBusy) return false;
  chatBusy = true;
  const history = [...messages, { role: 'user', content }].slice(-11);
  messages.push({ role: 'user', content });
  renderChat();
  $('chat-input').value = '';
  $('chat-send').disabled = true;
  $('question-send').disabled = true;
  $('chat-error').hidden = true;
  $('ai-status').textContent = 'Thinking…';
  try {
    const data = await api('/assistant', { method: 'POST', body: { messages: history } });
    messages.push({ role: 'assistant', content: data.reply });
    renderChat();
    return true;
  } catch (error) {
    messages.pop();
    renderChat();
    $('chat-input').value = content;
    $('chat-error').textContent = error.message;
    $('chat-error').hidden = false;
    return false;
  } finally {
    chatBusy = false;
    $('chat-send').disabled = !state.aiConfigured;
    $('question-send').disabled = !state.aiConfigured;
    $('ai-status').textContent = state.aiConfigured ? 'Connected' : 'Connect AI';
  }
}
$('chat-form').addEventListener('submit', async event => {
  event.preventDefault();
  await sendMessage($('chat-input').value.trim());
});
$('question-form').addEventListener('submit', async event => {
  event.preventDefault();
  const question = $('question-text').value.trim();
  if (!question) return;
  const context = $('question-context').value.trim();
  const content = `Please explain this question and its answer choices, including any tricky wording or explicit instructions. Help me identify which choice matches the facts I provide.\n\nQuestion and choices:\n${question}${context ? `\n\nMy context or uncertainty:\n${context}` : ''}`;
  $('assistant').scrollIntoView({ block: 'nearest' });
  await sendMessage(content);
});
$('export-data').addEventListener('click', () => {
  if (!state) return;
  const cell = value => {
    let text = String(value ?? '');
    if (/^(\s*[=+\-@]|[\t\r\n])/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  };
  const rows = [['Survey', 'Reward', 'Currency', 'Estimated minutes', 'Status', 'Added', 'Completed'], ...state.surveys.map(s => [s.title, (s.rewardCents / 100).toFixed(2), state.currency, s.minutes, s.status, s.createdAt, s.completedAt])];
  const blob = new Blob(['\ufeff' + rows.map(row => row.map(cell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = el('a');
  link.href = url;
  link.download = `surveyside-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
// Local-day totals update after midnight without requiring a reload.
setInterval(() => { if (state && !document.hidden) render(); }, 60_000);
refresh().catch(pageError);
