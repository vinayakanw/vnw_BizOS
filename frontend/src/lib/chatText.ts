// Text shown on the public chat page, in English and Hindi. The business's welcome message is theirs and is not translated.
export type Lang = 'en' | 'hi'

export const T = {
  en: {
    loading: 'Loading...',
    unavailable: 'This chat is not available',
    unavailableSub: 'The link may be wrong, or the business has not turned chat on yet.',
    chatWithUs: 'Chat with us',
    sales: 'Sales',
    support: 'Support',
    newChat: 'New chat',
    buy: 'I want to buy',
    buySub: 'Prices, products, quotes',
    help: 'I need help',
    helpSub: 'Orders, returns, warranty',
    name: 'Your name',
    email: 'Email',
    phone: 'Phone (optional)',
    start: 'Start chat',
    starting: 'Starting...',
    privacy: 'Your details are only used to answer you. Replies come from an AI assistant, and a team member can step in.',
    typing: 'Typing...',
    team: 'Team member',
    followUp: 'A team member will follow up with you',
    reference: 'Your reference is',
    placeholder: 'Type your message',
    send: 'Send',
    photo: 'Send a photo',
    photoBusy: 'Sending photo...',
    photoBad: 'Please choose a JPG, PNG or WebP photo.',
    emailChat: 'Email me this chat',
    emailSending: 'Sending...',
    emailSent: 'Sent to',
    emailFail: 'Could not send the email right now.',
    openQuote: 'Open quote',
    couldNot: 'Could not start the chat',
    inStock: 'In stock',
    outStock: 'Out of stock',
    askAbout: 'Ask about this',
    wantQuote: 'Get a quote',
    moreOptions: 'Show me other options',
    talkPerson: 'Talk to a person',
    s1: 'What do you sell?',
    s2: 'I need a quote',
    s3: 'Which is your most popular product?',
    h1: 'Where is my order?',
    h2: 'What is your return policy?',
    h3: 'My product has a problem',
    tellMore: (n: string) => `Tell me more about ${n}`,
    quoteFor: (n: string) => `I would like a quote for ${n}`,
    quoteGeneric: 'Can I get a quote?',
    otherOptions: 'What other options do you have?',
    personPlease: 'I would like to talk to a person',
  },
  hi: {
    loading: 'लोड हो रहा है...',
    unavailable: 'यह चैट उपलब्ध नहीं है',
    unavailableSub: 'लिंक गलत हो सकता है, या बिज़नेस ने अभी चैट चालू नहीं की है।',
    chatWithUs: 'हमसे चैट करें',
    sales: 'सेल्स',
    support: 'सपोर्ट',
    newChat: 'नई चैट',
    buy: 'मुझे खरीदना है',
    buySub: 'कीमत, प्रोडक्ट, कोटेशन',
    help: 'मुझे मदद चाहिए',
    helpSub: 'ऑर्डर, रिटर्न, वारंटी',
    name: 'आपका नाम',
    email: 'ईमेल',
    phone: 'फ़ोन (वैकल्पिक)',
    start: 'चैट शुरू करें',
    starting: 'शुरू हो रहा है...',
    privacy: 'आपकी जानकारी सिर्फ़ आपको जवाब देने के लिए इस्तेमाल होती है। जवाब AI असिस्टेंट देता है, और ज़रूरत पर टीम का सदस्य जुड़ सकता है।',
    typing: 'लिख रहा है...',
    team: 'टीम सदस्य',
    followUp: 'हमारी टीम का सदस्य आपसे संपर्क करेगा',
    reference: 'आपका रेफ़रेंस है',
    placeholder: 'अपना संदेश लिखें',
    send: 'भेजें',
    photo: 'फोटो भेजें',
    photoBusy: 'फोटो भेजी जा रही है...',
    photoBad: 'कृपया JPG, PNG या WebP फोटो चुनें।',
    emailChat: 'यह चैट मुझे ईमेल करें',
    emailSending: 'भेज रहे हैं...',
    emailSent: 'भेज दिया गया:',
    emailFail: 'अभी ईमेल नहीं भेज सके।',
    openQuote: 'कोटेशन खोलें',
    couldNot: 'चैट शुरू नहीं हो सकी',
    inStock: 'उपलब्ध',
    outStock: 'स्टॉक में नहीं',
    askAbout: 'इसके बारे में पूछें',
    wantQuote: 'कोटेशन चाहिए',
    moreOptions: 'और विकल्प दिखाइए',
    talkPerson: 'किसी व्यक्ति से बात करें',
    s1: 'आप क्या बेचते हैं?',
    s2: 'मुझे कोटेशन चाहिए',
    s3: 'आपका सबसे लोकप्रिय प्रोडक्ट कौन सा है?',
    h1: 'मेरा ऑर्डर कहाँ है?',
    h2: 'आपकी रिटर्न पॉलिसी क्या है?',
    h3: 'मेरे प्रोडक्ट में समस्या है',
    tellMore: (n: string) => `${n} के बारे में और बताइए`,
    quoteFor: (n: string) => `मुझे ${n} का कोटेशन चाहिए`,
    quoteGeneric: 'क्या मुझे कोटेशन मिल सकता है?',
    otherOptions: 'आपके पास और क्या विकल्प हैं?',
    personPlease: 'मैं किसी व्यक्ति से बात करना चाहता हूँ',
  },
} as const

export function initialLang(): Lang {
  try {
    const saved = localStorage.getItem('bizos_lang')
    if (saved === 'en' || saved === 'hi') return saved
  } catch {
    /* ignore */
  }
  return typeof navigator !== 'undefined' && navigator.language?.toLowerCase().startsWith('hi') ? 'hi' : 'en'
}

export function saveLang(l: Lang) {
  try {
    localStorage.setItem('bizos_lang', l)
  } catch {
    /* ignore */
  }
}
