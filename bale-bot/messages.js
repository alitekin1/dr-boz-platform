/**
 * Persian (Farsi) message strings used throughout the bot.
 * All user-facing text lives here for easy translation.
 */

export const M = {
  welcome: (firstName) =>
    `سلام ${firstName} 👋\n\n` +
    `من ربات رسمی **دکتر بز** هستم.\n` +
    `از اینجا می‌تونی اشتراک بخری و وارد مینی‌اپ بشی.`,

  needPhone: 'برای فعال‌سازی حساب، شماره موبایلت رو بفرست.\n' +
    'دکمه زیر رو بزن:',
  phoneThanks: 'شماره‌ات ثبت شد ✅',
  notContact: 'لطفاً فقط دکمه «اشتراک‌گذاری شماره» رو بزن.',

  openApp: '🚀 باز کردن دکتر بز',
  buyPlan: '💎 خرید اشتراک',
  myPlan: '📊 وضعیت اشتراک من',
  support: '🆘 پشتیبانی',
  sharePhone: '☎️ اشتراک‌گذاری شماره',

  plansHeader: 'طرح‌های اشتراک موجود:',
  planItem: (name, price) =>
    `• *${name}* — ${formatToman(price)} / ماه`,
  choosePlan: 'کدوم طرح رو می‌خوای؟ روی دکمه‌اش بزن.',

  payMethods: 'روش پرداخت رو انتخاب کن:',
  payBale: '💳 پرداخت از کیف پول بله',
  payCard: '🏦 کارت به کارت (تأیید توسط ادمین)',

  cardInfo: (holder, number) =>
    `برای پرداخت کارت به کارت، مبلغ رو به این کارت واریز کن:\n\n` +
    `👤 ${holder}\n` +
    `💳 \`${number}\`\n\n` +
    `بعد از واریز، **اسکرین‌شات رسید** رو همینجا بفرست ` +
    `(یا شماره پیگیری + مبلغ + ساعت رو تایپ کن).`,

  baleInvoiceSent: 'فاکتور پرداخت برات توی همین چت باز شد ✅',
  paymentOk: 'پرداخت موفق ✅ اشتراکت فعال شد.',
  paymentCancelled: 'پرداخت لغو شد.',
  paymentFailed: 'پرداخت ناموفق بود. دوباره تلاش کن یا با پشتیبانی تماس بگیر.',

  receiptReceived: 'رسید دریافت شد ✅ در حال ارسال برای ادمین...',
  receiptForwarded: 'رسید برای ادمین ارسال شد. منتظر تأیید باش.',
  receiptRejected: 'رسیدت توسط ادمین رد شد ❌ دوباره تلاش کن یا با پشتیبانی تماس بگیر.',

  adminOnly: '⛔ این دستور فقط برای ادمینه.',
  noPending: 'هیچ پرداخت کارت به کارتی در انتظار تأیید نیست ✅',
  pendingHeader: 'پرداخت‌های در انتظار تأیید:',
  pendingItem: (id, user, plan, amount) =>
    `• \`${id}\` — ${user} — ${plan} (${formatToman(amount)})`,
  approved: '✅ تأیید شد و اشتراک کاربر فعال شد.',
  rejected: '❌ رد شد.',
  badId: 'شناسه سفارش نامعتبر.',

  yourPlan: (status, expires) =>
    `وضعیت فعلی: *${status}*\n` +
    (expires ? `انقضا: ${expires}\n` : ''),
  noActivePlan: 'اشتراک فعالی نداری. از منو «خرید اشتراک» رو بزن.',
};

export function formatToman(n) {
  if (!n) return '۰ تومان';
  return new Intl.NumberFormat('fa-IR').format(n) + ' تومان';
}

export function planTypeToPersian(t) {
  return ({ free: 'رایگان', plus: 'پلاس', pro: 'حرفه‌ای' })[t] || t;
}
