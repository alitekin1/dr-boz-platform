/**
 * Dr. Boz Bale bot — zero-dependency fetch to tapi.bale.ai.
 * No node-telegram-bot-api needed.
 */
import 'dotenv/config';
import { readFileSync, existsSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import Redis from 'ioredis';
import { api } from './api.js';
import { M, formatToman } from './messages.js';

const TOKEN = process.env.BALE_BOT_TOKEN;
const BOT_USERNAME = (process.env.BALE_BOT_USERNAME || 'drboz_bale').replace(/^@/, '');
const ADMIN_IDS = (process.env.BOT_ADMIN_IDS || '').split(',').map(s => s.trim()).filter(Boolean);
const CARD_HOLDER = process.env.CARD_HOLDER_NAME || 'صاحب حساب';
const CARD_NUMBER = process.env.CARD_NUMBER || '0000-0000-0000-0000';

if (!TOKEN) { console.error('BALE_BOT_TOKEN not set'); process.exit(1); }

const __dirname = dirname(fileURLToPath(import.meta.url));
const BALE_API = `https://tapi.bale.ai/bot${TOKEN}`;

// ── Lightweight Bale API client (fetch only) ──────────────────────
async function bale(method, body = {}) {
  const res = await fetch(`${BALE_API}/${method}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  if (!json.ok) throw Object.assign(new Error(json.description || `Bale API ${json.error_code}`), { code: json.error_code });
  return json.result;
}

const sendMsg = (chat_id, text, extra = {}) => bale('sendMessage', { chat_id, text, ...extra });
const sendPhoto = (chat_id, photo, extra = {}) => bale('sendPhoto', { chat_id, photo, ...extra });
const sendInvoice = (chat_id, title, desc, payload, provider_token, currency, prices, extra = {}) =>
  bale('sendInvoice', { chat_id, title, description: desc, payload, provider_token, currency, prices, ...extra });
const answerCb = (cb_id, text, show_alert = false) => bale('answerCallbackQuery', { callback_query_id: cb_id, text, show_alert });
const answerPc = (pc_id, ok, error_message) => bale('answerPreCheckoutQuery', { pre_checkout_query_id: pc_id, ok, ...(error_message ? { error_message } : {}) });

// ── Phone cache (Redis or JSON file) ──────────────────────────────
let redis = null;
if (process.env.REDIS_URL) {
  try {
    redis = new Redis(process.env.REDIS_URL, { lazyConnect: true, maxRetriesPerRequest: 2 });
    redis.on('error', (e) => console.warn('redis err:', e.message));
    await redis.connect();
    console.log('phone cache: redis');
  } catch (e) { console.warn('redis fallback:', e.message); redis = null; }
}
const PHONE_FILE = join(__dirname, 'phone_cache.json');
const phoneMap = new Map();
if (existsSync(PHONE_FILE)) { try { const d = JSON.parse(readFileSync(PHONE_FILE, 'utf8')); for (const [k, v] of Object.entries(d)) phoneMap.set(k, v); } catch {} }
function persistPhones() { if (redis) return; try { writeFileSync(PHONE_FILE, JSON.stringify(Object.fromEntries(phoneMap), null, 2)); } catch {} }
async function setPhone(baleId, phone) { if (redis) await redis.setex(`bot:phone:${baleId}`, 90 * 86400, phone); else { phoneMap.set(String(baleId), phone); persistPhones(); } }
async function getPhone(baleId) { if (redis) return redis.get(`bot:phone:${baleId}`); return phoneMap.get(String(baleId)) || null; }

// ── Helpers ───────────────────────────────────────────────────────
const isAdmin = (id) => ADMIN_IDS.includes(String(id));
const mainAppUrl = () => 'https://ai.alitekin.space:3000/';
const orderMap = new Map();

const mainKeyboard = { keyboard: [[{ text: M.buyPlan }], [{ text: M.myPlan }, { text: M.support }]], resize_keyboard: true };
const requestPhoneKeyboard = { keyboard: [[{ text: M.sharePhone, request_contact: true }]], resize_keyboard: true, one_time_keyboard: true };

function plansKeyboard(plans) {
  return { inline_keyboard: plans.filter(p => Number(p.monthly_price_toman) > 0).map(p => [{ text: `${p.name} — ${formatToman(p.monthly_price_toman)}`, callback_data: `plan:${p.id}` }]) };
}
function payKeyboard(planId) {
  return { inline_keyboard: [[{ text: M.payBale, callback_data: `pay:bale:${planId}` }], [{ text: M.payCard, callback_data: `pay:card:${planId}` }], [{ text: '↩️ بازگشت', callback_data: 'plans' }]] };
}

// ── Handlers ──────────────────────────────────────────────────────
async function sendPlanList(chatId) {
  let plans; try { plans = await api.listPlans(); } catch { return sendMsg(chatId, '⚠️ خطا در دریافت طرح‌ها.'); }
  const paid = plans.filter(p => Number(p.monthly_price_toman) > 0);
  if (!paid.length) return sendMsg(chatId, '⚠️ فعلاً طرحی موجود نیست.');
  await sendMsg(chatId, [M.plansHeader, '', ...paid.map(p => M.planItem(p.name, p.monthly_price_toman))].join('\n'), { parse_mode: 'Markdown' });
  await sendMsg(chatId, M.choosePlan, { reply_markup: plansKeyboard(plans) });
}

async function doStart(msg) {
  const chatId = msg.chat.id, from = msg.from;
  await sendMsg(chatId, M.welcome(from.first_name || 'دوست عزیز'), { parse_mode: 'Markdown', reply_markup: mainKeyboard });
  if (!(await getPhone(from.id))) await sendMsg(chatId, M.needPhone, { reply_markup: requestPhoneKeyboard });
}

async function doContact(msg) {
  const chatId = msg.chat.id, from = msg.from;
  if (!msg.contact || (msg.contact.user_id && String(msg.contact.user_id) !== String(from.id))) return sendMsg(chatId, M.notContact);
  let phone = msg.contact.phone_number.replace(/\D/g, '');
  if (phone.startsWith('98') && phone.length === 12) phone = '+' + phone;
  else if (phone.startsWith('0') && phone.length === 11) phone = '+98' + phone.slice(1);
  else if (phone.length === 10 && phone.startsWith('9')) phone = '+98' + phone;
  else if (!phone.startsWith('+')) phone = '+' + phone;
  await setPhone(from.id, phone);
  return sendMsg(chatId, M.phoneThanks, { reply_markup: mainKeyboard });
}

async function doText(msg) {
  const chatId = msg.chat.id, text = msg.text;
  if (text === M.buyPlan) return sendPlanList(chatId);
  if (text === M.myPlan) return sendMsg(chatId, M.noActivePlan, { reply_markup: { inline_keyboard: [[{ text: M.openApp, web_app: { url: mainAppUrl() } }]] } });
  if (text === M.support) return sendMsg(chatId, 'پشتیبانی: @drboz_support');
}

async function doCallback(cq) {
  const data = cq.data || '', chatId = cq.message?.chat.id, from = cq.from;
  if (!chatId) return;
  if (data === 'plans') { await answerCb(cq.id, ''); return sendPlanList(chatId); }
  if (data.startsWith('plan:')) { await answerCb(cq.id, ''); return sendMsg(chatId, M.payMethods, { reply_markup: payKeyboard(data.slice(5)) }); }
  if (data.startsWith('pay:bale:')) { await answerCb(cq.id, 'در حال ساخت فاکتور...'); return doBaleInvoice(chatId, from, data.slice(9)); }
  if (data.startsWith('pay:card:')) { await answerCb(cq.id, ''); return doCardToCard(chatId, from, data.slice(9)); }
  if (data.startsWith('admin:approve:')) { if (!isAdmin(from.id)) return answerCb(cq.id, M.adminOnly);
    try { await api.adminApprove(from.id, data.slice(15)); await answerCb(cq.id, M.approved); } catch(e) { await answerCb(cq.id, '❌ '+e.message); } return; }
  if (data.startsWith('admin:reject:')) { if (!isAdmin(from.id)) return answerCb(cq.id, M.adminOnly);
    try { await api.adminReject(from.id, data.slice(14)); await answerCb(cq.id, M.rejected); } catch(e) { await answerCb(cq.id, '❌ '+e.message); } return; }
}

async function doBaleInvoice(chatId, from, planId) {
  let plans; try { plans = await api.listPlans(); } catch { return sendMsg(chatId, '⚠️ خطا.'); }
  const plan = plans.find(p => p.id === planId);
  if (!plan || Number(plan.monthly_price_toman) <= 0) return sendMsg(chatId, '⚠️ پلن نامعتبر.');
  const user = await getPhone(from.id);
  if (!user) return sendMsg(chatId, M.needPhone, { reply_markup: requestPhoneKeyboard });
  const lookup = await fetch(`${process.env.BACKEND_URL}/api/v1/billing/public/lookup-by-phone?phone=${encodeURIComponent(user)}`).then(r => r.ok ? r.json() : null).catch(() => null);
  if (!lookup?.id) return sendMsg(chatId, '⚠️ حسابت توی دکتر بز هنوز ساخته نشده.', { reply_markup: { inline_keyboard: [[{ text: M.openApp, web_app: { url: mainAppUrl() } }]] } });
  let order; try { order = await api.createOrder({ user_id: lookup.id, bale_user_id: String(from.id), plan_id: plan.id }); } catch(e) { console.error(e); return sendMsg(chatId, '⚠️ خطا در ساخت سفارش.'); }
  try {
    await sendInvoice(chatId, `اشتراک ${plan.name} دکتر بز`, `پلن ${plan.name} — ${formatToman(plan.monthly_price_toman)} / ماه`, order.id, '', 'IRR',
      [{ label: plan.name, amount: Number(plan.monthly_price_toman) * 10 }], { need_name: false, need_phone_number: false, need_email: false, is_flexible: false });
  } catch(e) { console.error(e); await api.cancelOrder(order.id).catch(() => {}); return sendMsg(chatId, '⚠️ خطا در ارسال فاکتور. کیف پولت فعاله؟'); }
}

async function doPreCheckout(qc) {
  try { const order = await api.getOrder(qc.id);
    return answerPc(qc.id, !!(order && order.status === 'awaiting_invoice'), 'سفارش منقضی شده.');
  } catch { return answerPc(qc.id, false, 'خطای سرور'); }
}

async function doSuccessfulPayment(msg) {
  const sp = msg.successful_payment, chatId = msg.chat.id;
  try { await api.markPaid(sp.invoice_payload); } catch { return sendMsg(chatId, '⚠️ خطا در فعال‌سازی اشتراک.'); }
  return sendMsg(chatId, M.paymentOk, { reply_markup: { inline_keyboard: [[{ text: M.openApp, web_app: { url: mainAppUrl() } }]] } });
}

async function doCardToCard(chatId, from, planId) {
  let plans; try { plans = await api.listPlans(); } catch { return sendMsg(chatId, '⚠️ خطا.'); }
  const plan = plans.find(p => p.id === planId);
  if (!plan) return sendMsg(chatId, '⚠️ پلن نامعتبر.');
  const user = await getPhone(from.id);
  if (!user) return sendMsg(chatId, M.needPhone, { reply_markup: requestPhoneKeyboard });
  const lookup = await fetch(`${process.env.BACKEND_URL}/api/v1/billing/public/lookup-by-phone?phone=${encodeURIComponent(user)}`).then(r => r.ok ? r.json() : null).catch(() => null);
  if (!lookup?.id) return sendMsg(chatId, '⚠️ حسابت توی دکتر بز هنوز ساخته نشده.', { reply_markup: { inline_keyboard: [[{ text: M.openApp, web_app: { url: mainAppUrl() } }]] } });
  let order; try { order = await api.createOrder({ user_id: lookup.id, bale_user_id: String(from.id), plan_id: plan.id }); } catch(e) { return sendMsg(chatId, '⚠️ خطا در ساخت سفارش.'); }
  if (redis) await redis.setex(`bot:order:${from.id}`, 3600, order.id); else orderMap.set(String(from.id), order.id);
  return sendMsg(chatId, M.cardInfo(CARD_HOLDER, CARD_NUMBER), { parse_mode: 'Markdown', reply_markup: { remove_keyboard: true } });
}

async function doPhoto(msg) {
  const from = msg.from; if (!from || !ADMIN_IDS.length) return;
  let orderId; if (redis) orderId = await redis.get(`bot:order:${from.id}`); else orderId = orderMap.get(String(from.id));
  if (!orderId) return;
  await sendMsg(msg.chat.id, M.receiptReceived);
  const photo = msg.photo[msg.photo.length - 1];
  const caption = `📥 رسید\nاز: ${from.first_name||''} ${from.username ? '@'+from.username : ''} (id=${from.id})\nسفارش: \`${orderId}\``;
  for (const adminId of ADMIN_IDS) {
    try { await sendPhoto(adminId, photo.file_id, { caption, parse_mode: 'Markdown', reply_markup: { inline_keyboard: [[{ text: '✅ تأیید', callback_data: `admin:approve:${orderId}` }, { text: '❌ رد', callback_data: `admin:reject:${orderId}` }]] } }); } catch(e) { console.warn('fwd admin fail:', e.message); }
  }
  await sendMsg(msg.chat.id, M.receiptForwarded);
  if (redis) await redis.del(`bot:order:${from.id}`); else orderMap.delete(String(from.id));
}

async function doAdminCommand(msg, cmd, arg) {
  if (!isAdmin(msg.from.id)) return sendMsg(msg.chat.id, M.adminOnly);
  const chatId = msg.chat.id;
  if (cmd === '/pending') { let o; try { o = await api.adminListPending(msg.from.id); } catch(e) { return sendMsg(chatId, '⚠️ '+e.message); }
    if (!o.length) return sendMsg(chatId, M.noPending);
    return sendMsg(chatId, [M.pendingHeader, '', ...o.map(x => M.pendingItem(x.id, x.bale_user_id||x.user_id, x.plan_name||x.plan_id, x.amount_toman))].join('\n'), { parse_mode: 'Markdown' }); }
  if (cmd === '/approve' && arg) { try { await api.adminApprove(msg.from.id, arg); return sendMsg(chatId, M.approved); } catch(e) { return sendMsg(chatId, '⚠️ '+e.message); } }
  if (cmd === '/reject' && arg) { try { await api.adminReject(msg.from.id, arg); return sendMsg(chatId, M.rejected); } catch(e) { return sendMsg(chatId, '⚠️ '+e.message); } }
}

// ── Dispatch ──────────────────────────────────────────────────────
async function processUpdate(u) {
  if (u.message) {
    const m = u.message;
    if (m.text && m.text.startsWith('/')) { const [cmd, ...args] = m.text.split(/\s+/);
      if (cmd === '/start') return doStart(m);
      if (['/pending','/approve','/reject'].includes(cmd)) return doAdminCommand(m, cmd, args[0]);
    }
    if (m.contact) return doContact(m);
    if (m.photo) return doPhoto(m);
    if (m.text) return doText(m);
    if (m.successful_payment) return doSuccessfulPayment(m);
  }
  if (u.callback_query) return doCallback(u.callback_query);
  if (u.pre_checkout_query) return doPreCheckout(u.pre_checkout_query);
}

// ── Polling loop ──────────────────────────────────────────────────
console.log(`Dr. Boz Bale bot started (@${BOT_USERNAME})`);

let offset = 0;
async function poll() {
  let failCount = 0;
  for (;;) {
    try {
      const updates = await bale('getUpdates', { offset, timeout: 25, allowed_updates: ['message','callback_query','pre_checkout_query'] });
      for (const u of updates) {
        try {
          await processUpdate(u);
          offset = u.update_id + 1;
        } catch (e) {
          console.error(`[update ${u.update_id}]`, e.message);
          offset = u.update_id + 1; // skip bad update
        }
      }
      failCount = 0;
    } catch (e) {
      failCount++;
      console.error(`poll #${failCount}:`, e.message);
      if (failCount > 10) { console.error('Too many poll failures, restart needed'); process.exit(1); }
      await new Promise(r => setTimeout(r, 2000 * failCount));
    }
  }
}

poll().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
