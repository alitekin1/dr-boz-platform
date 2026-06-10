
const PptxGenJS = require('pptxgenjs');
const fs = require('fs');

let pptx = new PptxGenJS();
pptx.layout = 'LAYOUT_16x9';
pptx.author = 'گروه الهه کاظمیان';
pptx.title = 'تغذیه مناسب برای فعالیت بدنی روزمره';
pptx.subject = 'تغذیه ورزشی روزمره';

const colors = {
  bg: 'FAF9F6',
  primary: '6B8E23',
  secondary: '98FB98',
  accent: 'FF8C00',
  text: '333333',
  textLight: '666666'
};

const titleOpts = {
  x: 1.0, y: 0.8, w: 8.0, h: 1.0,
  fontSize: 42, bold: true, color: colors.primary,
  fontFace: 'Tahoma',
  dir: 'rtl', align: 'center'
};

const subtitleOpts = {
  x: 1.0, y: 1.8, w: 8.0, h: 0.8,
  fontSize: 28, color: colors.text, 
  fontFace: 'Arial',
  dir: 'rtl', align: 'center', italic: true
};

const bodyOpts = {
  x: 1.0, y: 2.8, w: 8.5, h: 2.5,
  fontSize: 26, color: colors.text,
  fontFace: 'Arial',
  dir: 'rtl', bullet: true, bulletSize: 150,
  lineSpacing: 8
};

const membersOpts = {
  x: 1.0, y: 4.0, w: 8.5, h: 1.0,
  fontSize: 20, color: colors.textLight,
  fontFace: 'Arial',
  dir: 'rtl', align: 'center'
};

// Slide 1: Title
let slide1 = pptx.addSlide();
slide1.background = { color: colors.bg };
slide1.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:0.5, w:0.4, h:4.5, fill: {color: colors.accent}, roundRectRadius: 0.2 });
slide1.addText('تغذیه مناسب برای فعالیت بدنی روزمره', titleOpts);
slide1.addText('کلید افزایش انرژی، ریکاوری و عملکرد بهتر', subtitleOpts);
slide1.addText('اعضای گروه: الهه کاظمیان، فاطمه علیزاده، الناز خزاعی پور، بهاره خانجانی', membersOpts);

// Slide 2: هدف و اهمیت
let slide2 = pptx.addSlide();
slide2.background = { color: colors.bg };
slide2.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:1.0, w:0.4, h:3.5, fill: {color: colors.primary}, roundRectRadius: 0.2 });
slide2.addText('هدف و اهمیت', { ...titleOpts, y:1.2 });
slide2.addText([
  { text: '• تغذیه، نقش مهم‌تری از مکمل‌ها دارد.', options: { breakLine: true } },
  { text: '• بدون سوخت صحیح، فعالیت بدنی نه تنها مفید نیست، بلکه به تحلیل عضلات و خستگی مزمن منجر می‌شود.', options: { breakLine: true } },
  { text: '• هدف: آشنایی با زمان، نوع و مقدار مواد مغذی پیش، حین و بعد از ورزش.' }
], bodyOpts);

// Slide 3: مثلث انرژی
let slide3 = pptx.addSlide();
slide3.background = { color: colors.bg };
slide3.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:1.0, w:0.4, h:3.5, fill: {color: colors.primary}, roundRectRadius: 0.2 });
slide3.addText('مثلث انرژی فعالیت روزانه', { ...titleOpts, y:1.2 });
slide3.addShape(pptx.shapes.RECTANGLE, { x:2.5, y:3.2, w:5.0, h:1.0, fill: {color: colors.secondary}, roundRectRadius: 0.1 });
slide3.addText('کربوهیدرات (سوخت اصلی)', { x:2.5, y:3.3, w:5.0, h:0.8, fontSize:22, color:colors.text, dir:'rtl', fontFace:'Arial' });
slide3.addShape(pptx.shapes.RECTANGLE, { x:3.5, y:2.6, w:3.0, h:0.8, fill: {color: colors.accent}, roundRectRadius: 0.1 });
slide3.addText('چربی (سوخت ذخیره‌ای برای فعالیت طولانی)', { x:3.5, y:2.7, w:3.0, h:0.6, fontSize:20, color:colors.text, dir:'rtl', fontFace:'Arial' });
slide3.addShape(pptx.shapes.RECTANGLE, { x:4.5, y:2.1, w:1.0, h:0.6, fill: {color: colors.primary}, roundRectRadius: 0.1 });
slide3.addText('پروتئین (تعمیر و ساخت عضله)', { x:4.5, y:2.2, w:1.0, h:0.4, fontSize:18, color:'FFFFFF', dir:'rtl', fontFace:'Arial', align:'center' });
slide3.addText('نکته: در فعالیت روزمره (نه حرفه‌ای)، کربوهیدرات ۵۵-۶۰٪ انرژی را تأمین می‌کند.', { x:1.0, y:4.0, w:8.5, h:0.8, fontSize:22, color:colors.textLight, dir:'rtl', italic:true });

// Slide 4: کربوهیدرات‌ها
let slide4 = pptx.addSlide();
slide4.background = { color: colors.bg };
slide4.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:1.0, w:0.4, h:3.5, fill: {color: colors.primary}, roundRectRadius: 0.2 });
slide4.addText('کربوهیدرات‌ها – دوست فعالیت روزانه', { ...titleOpts, y:1.2 });
slide4.addText([
  { text: 'قبل از فعالیت: نان سبوس‌دار، برنج قهوه‌ای، جو دوسر، موز', options: { breakLine: true } },
  { text: 'بعد از فعالیت: همراه با کمی پروتئین برای بازسازی ذخیره گلیکوژن', options: { breakLine: true } },
  { text: 'خوب است بدانیم: حذف کربوهیدرات برای افراد فعال منجر به افت زودهنگام انرژی می‌شود.' }
], bodyOpts);

// Continue for other slides similarly...
// Slide 5
let slide5 = pptx.addSlide();
slide5.background = { color: colors.bg };
slide5.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:1.0, w:0.4, h:3.5, fill: {color: colors.primary}, roundRectRadius: 0.2 });
slide5.addText('پروتئین – نه فقط برای بدنسازان', { ...titleOpts, y:1.2 });
slide5.addText([
  { text: 'نیاز روزانه افراد عمومی: حدود ۱.۲ تا ۱.۷ گرم به ازای هر کیلو وزن بدن (در صورت فعالیت منظم)', options: { breakLine: true } },
  { text: 'منابع: تخم‌مرغ، لبنیات، حبوبات، گوشت سفید، سویا', options: { breakLine: true } },
  { text: 'توزیع متوازن پروتئین در سه وعده اصلی، بهتر از یک وعده زیاد است.' }
], bodyOpts);

// Slide 6
let slide6 = pptx.addSlide();
slide6.background = { color: colors.bg };
slide6.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:1.0, w:0.4, h:3.5, fill: {color: colors.primary}, roundRectRadius: 0.2 });
slide6.addText('چربی‌های خوب – نباید ترسید', { ...titleOpts, y:1.2 });
slide6.addText([
  { text: 'چربی‌های غیراشباع (آووکادو، مغزها، روغن زیتون، ماهی) به مفاصل و جذب ویتامین‌ها کمک می‌کنند.', options: { breakLine: true } },
  { text: 'قبل از فعالیت سنگین، وعده پرچرب سنگین نخورید (هضم کند دارد).', options: { breakLine: true } },
  { text: 'مصرف روزانه چربی در افراد فعال: حدود ۲۵-۳۰٪ کالری روزانه.' }
], bodyOpts);

// Slide 7
let slide7 = pptx.addSlide();
slide7.background = { color: colors.bg };
slide7.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:1.0, w:0.4, h:3.5, fill: {color: colors.primary}, roundRectRadius: 0.2 });
slide7.addText('آب و الکترولیت‌ها – فراموش شده مهم‌ترین', { ...titleOpts, y:1.2 });
slide7.addText([
  { text: 'کاهش ۲ درصد آب بدن = کاهش ۲۰ درصد عملکرد جسمی و ذهنی', options: { breakLine: true } },
  { text: 'نشانه‌های کم آبی خفیف: خشکی دهان، سردرد، کاهش تمرکز', options: { breakLine: true } },
  { text: 'در فعالیت روزمره ۱ ساعت: آب کافی است. بیش از ۱ ساعت یا تعریق شدید: آب + سدیم/پتاسیم.' }
], bodyOpts);

// Slide 8
let slide8 = pptx.addSlide();
slide8.background = { color: colors.bg };
slide8.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:1.0, w:0.4, h:3.5, fill: {color: colors.primary}, roundRectRadius: 0.2 });
slide8.addText('وعده قبل از فعالیت (نکات کاربردی)', { ...titleOpts, y:1.2 });
slide8.addText([
  { text: 'زمان: ۱ تا ۳ ساعت قبل', options: { breakLine: true } },
  { text: 'مثال: یک موز + یک قاشق کره بادام زمینی + یک لیوان آب', options: { breakLine: true } },
  { text: 'از غذاهای حجیم، پرچرب و پر فیبر پرهیز کنید.' }
], bodyOpts);

// Slide 9
let slide9 = pptx.addSlide();
slide9.background = { color: colors.bg };
slide9.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:1.0, w:0.4, h:3.5, fill: {color: colors.primary}, roundRectRadius: 0.2 });
slide9.addText('تغذیه حین فعالیت (آیا نیاز است؟)', { ...titleOpts, y:1.2 });
slide9.addText([
  { text: 'فعالیت کمتر از ۴۵-۶۰ دقیقه: فقط آب کافی است.', options: { breakLine: true } },
  { text: 'بیشتر از ۶۰ دقیقه: نیاز به کربوهیدرات سریع (آب سیب رقیق، ژل ورزشی، موز) هر ۲۰-۳۰ دقیقه.', options: { breakLine: true } },
  { text: 'در فعالیت روزمره مثل پیاده‌روی سریع ۱ ساعته، فقط آب کافی است.' }
], bodyOpts);

// Slide 10
let slide10 = pptx.addSlide();
slide10.background = { color: colors.bg };
slide10.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:1.0, w:0.4, h:3.5, fill: {color: colors.primary}, roundRectRadius: 0.2 });
slide10.addText('صفحه طلایی – بازسازی بعد از فعالیت', { ...titleOpts, y:1.2 });
slide10.addText([
  { text: 'پنجره بازسازی طلایی: ۳۰ تا ۶۰ دقیقه اول بعد از تمرین', options: { breakLine: true } },
  { text: 'نسبت پیشنهادی: ۳ یا ۴ به ۱ (کربوهیدرات به پروتئین)', options: { breakLine: true } },
  { text: 'مثال: یک لیوان شیر شکلات + یک عدد خرما، یا ماست یونانی + عسل + گردو.' }
], bodyOpts);

// Slide 11: اشتباهات
let slide11 = pptx.addSlide();
slide11.background = { color: colors.bg };
slide11.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:1.0, w:0.4, h:3.5, fill: {color: 'FF4500'}, roundRectRadius: 0.2 }); // red accent for mistakes
slide11.addText('اشتباهات رایج در تغذیه روزمره فعالان', { ...titleOpts, y:1.2, color: 'FF4500' });
slide11.addText([
  { text: 'ورزش ناشتا (کاهش متابولیسم و تحلیل عضله)', options: { breakLine: true } },
  { text: 'نخوردن بعد از تمرین برای لاغری سریع‌تر (کاهش ریکاوری)', options: { breakLine: true } },
  { text: 'اتکا به نوشیدنی‌های انرژی‌زا (قند بالا + ضربان نامنظم)', options: { breakLine: true } },
  { text: 'کمبود خواب = هوس غذایی و اختلال در جذب مواد.' }
], bodyOpts);

// Slide 12: برنامه عملی
let slide12 = pptx.addSlide();
slide12.background = { color: colors.bg };
slide12.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:1.0, w:0.4, h:3.5, fill: {color: colors.primary}, roundRectRadius: 0.2 });
slide12.addText('یک برنامه عملی ساده (مثال برای یک روز معمولی)', { ...titleOpts, y:1.2 });
let tableData = [
  [{ text: 'زمان', options: { bold: true, fill: { color: colors.primary }, color: 'FFFFFF', dir: 'rtl' } }, { text: 'خوراک', options: { bold: true, fill: { color: colors.primary }, color: 'FFFFFF', dir: 'rtl' } }, { text: 'دلیل', options: { bold: true, fill: { color: colors.primary }, color: 'FFFFFF', dir: 'rtl' } }],
  [{ text: 'صبحانه قبل از پیاده‌روی', options: { dir: 'rtl' } }, { text: '۲ قاشق جو دوسر + شیر + نصف موز', options: { dir: 'rtl' } }, { text: 'سوخت سریع و پایدار', options: { dir: 'rtl' } }],
  [{ text: 'میان‌وعده قبل از ناهار', options: { dir: 'rtl' } }, { text: 'یک سیب + چند بادام', options: { dir: 'rtl' } }, { text: 'انرژی مداوم', options: { dir: 'rtl' } }],
  [{ text: 'بعد از ورزش عصر (۳۰ دقیقه)', options: { dir: 'rtl' } }, { text: 'دو عدد خرما + دو لیوان آب', options: { dir: 'rtl' } }, { text: 'بازسازی سریع', options: { dir: 'rtl' } }],
  [{ text: 'شام ریکاوری', options: { dir: 'rtl' } }, { text: 'کباب تابه‌ای مرغ + برنج کته + سالاد + ماست', options: { dir: 'rtl' } }, { text: 'تعمیر کامل', options: { dir: 'rtl' } }]
];
slide12.addTable(tableData, { x: 1.0, y: 2.5, w: 8.5, h: 2.5, colW: [2.5, 3, 3], fill: { color: 'FFFFFF' }, border: { pt: 1, color: colors.textLight } });

// Slide 13: جمع‌بندی
let slide13 = pptx.addSlide();
slide13.background = { color: colors.bg };
slide13.addShape(pptx.shapes.RECTANGLE, { x:0.2, y:0.5, w:0.4, h:4.5, fill: {color: colors.accent}, roundRectRadius: 0.2 });
slide13.addText('جمع‌بندی و نکات کلیدی', titleOpts);
slide13.addText([
  { text: '1. کربوهیدرات سوخت اصلی فعالیت روزمره است.', options: { breakLine: true, bold: true } },
  { text: '2. پروتئین و چربی‌های خوب را در وعده‌ها پخش کنید.', options: { breakLine: true } },
  { text: '3. هیدراته ماندن مهم‌تر از چیزی است که فکر می‌کنید.', options: { breakLine: true } },
  { text: '4. قبل و بعد ورزش کم نخورید؛ درست بخورید.', options: { breakLine: true } },
  { text: '5. این اصول را متناسب با ساعت و شدت فعالیت خود تنظیم کنید.' }
], { ...bodyOpts, y: 2.2, fontSize: 24 });

pptx.writeFile({ fileName: 'taghzieh_faaliat_badani.pptx' });
console.log('PPTX generated successfully');
