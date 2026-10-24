// Every user-facing label in one place, in plain marketing language.

export const PRINCIPLE = 'Simulation filters; reality judges.';

export const ORG_FIELDS = {
  website: ['Website', 'https://'],
  industry: ['Industry or category', 'Video games, coaching, bakery…'],
  description: ['Short description', 'What you do, in a sentence or two'],
  market: ['Primary market or location', 'UK and Ireland, Bangalore…'],
  customers: ['Target customers', 'Who you sell to'],
  voice: ['Brand voice', 'Warm, playful, never pushy'],
  colours: ['Brand colours', '#107C10 #FFFFFF'],
  competitors: ['Competitors', 'Names or websites, separated by commas'],
  notes: ['Additional notes', 'Anything else we should know'],
};

export const PRODUCT_FIELDS = {
  description: ['Description', 'What it is'],
  category: ['Category', 'Subscription, course, device…'],
  customers: ['Intended customers', 'Who it is for'],
  problems: ['Customer problems', 'What it solves'],
  value_proposition: ['Value proposition', 'Why people choose it'],
  features: ['Features', 'What it includes'],
  benefits: ['Benefits', 'What people get out of it'],
  proof_points: ['Proof points', 'Numbers, awards, reviews you can back up'],
  pricing: ['Pricing or offer', 'Price, trial, discount'],
  links: ['Website links', 'Product page, store page'],
  brand_requirements: ['Brand requirements', 'Logo use, naming, colours'],
  prohibited_claims: ['Claims that must not be made', 'Things we can never say'],
};

export const CAMPAIGN_FIELDS = {
  goal: ['Campaign goal', '5,000 trial sign-ups in December'],
  audience: ['Target audience', 'Who this campaign is for'],
  market: ['Market or location', 'Where it runs'],
  platforms: ['Platforms', 'Instagram, TikTok, YouTube…'],
  format: ['Content format', 'Reels, images, carousels'],
  offer: ['Offer', 'What people get'],
  destination: ['Destination or call to action', 'Where people land and what they do'],
  start: ['Start date', ''],
  end: ['End date', ''],
  budget: ['Budget', 'Optional'],
  success_metric: ['Success measurement', 'How we will know it worked'],
  required_messages: ['Required messages', 'One per line'],
  required_assets: ['Required assets', 'Reel, image, captions…'],
  brand_rules: ['Brand rules', 'Tone, colours, words you never use'],
  prohibited_claims: ['Prohibited claims', 'Claims we must never make'],
  language: ['Language', 'English'],
  tone: ['Tone', 'Festive, warm'],
  instructions: ['Additional instructions', 'Anything else'],
};

export const BRIEF_FIELDS = {
  objective: 'Objective',
  audience: 'Audience',
  insight: 'Customer insight',
  offer: 'Product or offer',
  main_message: 'Main message',
  evidence: 'Supporting evidence',
  action: 'Desired customer action',
  platforms_formats: 'Platforms and formats',
  creative_direction: 'Creative direction',
  brand_requirements: 'Brand requirements',
  restrictions: 'Restrictions',
  success_metric: 'Success measurement',
};

export const OBJECTIVES = {
  'awareness': ['◎', 'More of the right people know you exist'],
  'qualified inquiries': ['✉', 'Calls, forms and messages from real prospects'],
  'registrations': ['✎', 'Sign-ups for an event, demo or trial'],
  'enrollment': ['◆', 'Seats filled in a course or programme'],
  'visits': ['⌂', 'Footfall, bookings or site visits'],
  'installations': ['⇩', 'App installs from the right audience'],
  'sales': ['₹', 'Orders and revenue'],
  'evidence of demand': ['⚑', 'Proof people want it before you build'],
};

export const PROV = {
  provided: ['Provided by you', 'You told us this, or it is in your own materials.'],
  research: ['Found through research', 'Found in a public source. Check the source before relying on it.'],
  ai: ['Suggested by AI', 'Our reading of your materials, not a stated fact.'],
  unconfirmed: ['Unconfirmed', 'We could not find this in any source. Treat it as a guess.'],
  missing: ['Missing', 'Not in your materials or in public sources.'],
};

export const METRICS = {
  reach: 'Reach', impressions: 'Impressions', clicks: 'Clicks', signups: 'Sign-ups', purchases: 'Purchases',
  saves: 'Saves', shares: 'Shares', comments: 'Comments', replies: 'Replies', reposts: 'Reposts',
  watch_time: 'Watch time (s)', avg_view_duration: 'Avg. view (s)', completion_rate: 'Completion rate',
  rewatches: 'Rewatches', cost: 'Cost', revenue: 'Revenue',
};

export const STEPS = [
  ['brief', 'Brief'], ['concepts', 'Concepts'], ['assets', 'Assets'], ['launch', 'Launch'],
  ['results', 'Results'], ['next', 'Next experiment'],
];

export const REACTIONS = { share: 'would share', engage: 'would engage', ignore: 'scrolled past', dislike: 'annoyed' };

export const ROLES = {
  product: 'Product', character: 'Character / spokesperson', location: 'Location', style: 'Style reference',
  logo: 'Logo', music: 'Music track', font: 'Font', reference_reel: 'Reference Reel',
};

export const ASSET_TYPES = {
  motion_graphics: 'Motion graphics', uploaded_asset: 'Your upload', generated_image: 'Generated image',
  generated_video: 'Generated video', stock_video: 'Stock footage',
};

export const CRITERIA = {
  hook: 'First 3 seconds', clarity: 'Message clarity', visual_relevance: 'Visual relevance',
  brand_consistency: 'Brand consistency', product_accuracy: 'Product accuracy', continuity: 'Scene continuity',
  pacing: 'Pacing', caption_readability: 'Caption readability', audio_balance: 'Audio balance',
  cta_clarity: 'Call to action', platform_fit: 'Platform fit', visual_quality: 'Visual quality',
};

export const REEL_STAGES = { storyboard: 'Storyboard', assets: 'Visuals', voice: 'Voice', captions: 'Captions',
  critic: 'Quality review', preview: 'Preview', review: 'Frame review', final: 'Final export' };
