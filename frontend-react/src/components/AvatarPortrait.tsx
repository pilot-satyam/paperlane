type AvatarStyle = {
  name: string;
  background: string;
  splash: string;
  skin: string;
  hair: string;
  jacket: string;
  detail: string;
  hairStyle: 'spikes' | 'bob' | 'sweep' | 'waves';
  accessory: 'glasses' | 'headphones' | 'star' | 'mask' | 'none';
};

export const AVATAR_STYLES: AvatarStyle[] = [
  { name: 'Neon rider', background: '#163f4f', splash: '#41e7d6', skin: '#e8ad87', hair: '#22c8e0', jacket: '#f06a83', detail: '#ffd27a', hairStyle: 'spikes', accessory: 'headphones' },
  { name: 'Violet rebel', background: '#43305e', splash: '#f17bd5', skin: '#c88467', hair: '#a889fb', jacket: '#26364f', detail: '#f6ce75', hairStyle: 'waves', accessory: 'star' },
  { name: 'Sunset skater', background: '#6b3442', splash: '#ffbb6c', skin: '#f4c49e', hair: '#f78851', jacket: '#304966', detail: '#78e6cb', hairStyle: 'sweep', accessory: 'none' },
  { name: 'Mint maker', background: '#254b46', splash: '#b9f18e', skin: '#a86b53', hair: '#7adb9d', jacket: '#694783', detail: '#f6d275', hairStyle: 'bob', accessory: 'glasses' },
  { name: 'Coral comet', background: '#5a3752', splash: '#ff849b', skin: '#df9d79', hair: '#f5a2bf', jacket: '#24645e', detail: '#f9df92', hairStyle: 'bob', accessory: 'star' },
  { name: 'Arcade ace', background: '#27375c', splash: '#83aaff', skin: '#d7a77d', hair: '#506be0', jacket: '#eb9a51', detail: '#baf4dc', hairStyle: 'spikes', accessory: 'headphones' },
  { name: 'Golden glitch', background: '#5e452f', splash: '#f5d46b', skin: '#9a6048', hair: '#f1c662', jacket: '#345d65', detail: '#f59ab7', hairStyle: 'waves', accessory: 'glasses' },
  { name: 'Night ninja', background: '#283a45', splash: '#a7f0b0', skin: '#efbb99', hair: '#273141', jacket: '#7456a2', detail: '#79e8dd', hairStyle: 'sweep', accessory: 'mask' },
];

export function avatarForAccount(id: string): number {
  let hash = 2166136261;
  for (const char of id) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return (hash >>> 0) % AVATAR_STYLES.length;
}

export default function AvatarPortrait({ variant }: { variant: number }) {
  const style = AVATAR_STYLES[Number.isInteger(variant) && variant >= 0 && variant < AVATAR_STYLES.length ? variant : 0];
  return <svg viewBox="0 0 64 64" width="100%" height="100%" aria-hidden="true" focusable="false">
    <rect width="64" height="64" rx="13" fill={style.background}/>
    <path d="M-3 18 35-5M30 67 70 22" stroke={style.splash} strokeWidth="8" opacity=".28"/>
    <path d="M4 40 17 35M49 12 61 8M48 47 62 42" stroke={style.splash} strokeWidth="2.5" strokeLinecap="round" opacity=".8"/>
    <circle cx="11" cy="15" r="3" fill={style.splash} opacity=".75"/><circle cx="53" cy="25" r="2" fill={style.detail} opacity=".9"/>
    <path d="M5 64C7 52 17 47 27 45h10c11 2 20 7 22 19Z" fill={style.jacket}/>
    <path d="M25 46 32 54 39 46" fill="none" stroke={style.detail} strokeWidth="3" strokeLinejoin="round"/>
    <rect x="27" y="39" width="10" height="10" rx="4" fill={style.skin}/>
    {style.hairStyle === 'waves' && <path d="M17 24c-4 7-3 25-7 27 6 3 10-2 10-7h24c0 8 5 10 11 7-5-7-2-20-7-29Z" fill={style.hair}/>}
    {style.hairStyle === 'bob' && <path d="M16 22c-4 10-1 22-2 27l8-2 2-11h17l1 11 8 2c-1-7 2-19-3-28Z" fill={style.hair}/>}
    <ellipse cx="17" cy="31" rx="3" ry="5" fill={style.skin}/><ellipse cx="47" cy="31" rx="3" ry="5" fill={style.skin}/>
    <ellipse cx="32" cy="29" rx="15" ry="18" fill={style.skin}/>
    <path d="M17 25c-1-12 5-20 15-20 11 0 17 7 15 20-3-6-6-9-10-10-5 8-14 8-20 10Z" fill={style.hair}/>
    {style.hairStyle === 'spikes' && <path d="m16 20 2-15 7 7 5-9 6 8 9-7 2 16c-10-8-20-9-31 0Z" fill={style.hair}/>}
    {style.hairStyle === 'sweep' && <path d="M16 23c3-15 15-21 28-16 4 3 6 7 5 13-10-4-19-2-31 8Z" fill={style.hair}/>}
    {style.hairStyle === 'bob' && <path d="M17 26c1-14 8-20 18-20 8 0 14 8 13 20-5-7-7-13-10-13-5 7-12 11-21 13Z" fill={style.hair}/>}
    {style.hairStyle === 'waves' && <path d="M17 25c-2-12 5-20 14-20 8 0 16 5 17 18-5-6-7-7-10-8-5 7-14 10-21 10Z" fill={style.hair}/>}
    <path d="M21 27q4-3 8 0M35 27q4-3 8 0" fill="none" stroke="#47333b" strokeWidth="1.6" strokeLinecap="round"/>
    <ellipse cx="26" cy="31" rx="3.4" ry="4" fill="#fff8f0"/><ellipse cx="38" cy="31" rx="3.4" ry="4" fill="#fff8f0"/>
    <ellipse cx="26.4" cy="31.8" rx="1.7" ry="2.5" fill="#223846"/><ellipse cx="38.4" cy="31.8" rx="1.7" ry="2.5" fill="#223846"/>
    <circle cx="27" cy="30.6" r=".7" fill="white"/><circle cx="39" cy="30.6" r=".7" fill="white"/>
    <ellipse cx="20.4" cy="36" rx="2.5" ry="1.2" fill="#e77f8c" opacity=".65"/><ellipse cx="43.6" cy="36" rx="2.5" ry="1.2" fill="#e77f8c" opacity=".65"/>
    <path d="M30 39q2 2 4 0" fill="none" stroke="#8c4e5b" strokeWidth="1.4" strokeLinecap="round"/>
    {style.accessory === 'glasses' && <g fill="none" stroke={style.detail} strokeWidth="2"><rect x="20" y="27" width="11" height="9" rx="4"/><rect x="33" y="27" width="11" height="9" rx="4"/><path d="M31 30h2M17 29h3M44 29h3"/></g>}
    {style.accessory === 'headphones' && <g fill="none" stroke={style.detail} strokeWidth="2.6"><path d="M17 28c-1-14 5-20 15-20s16 6 15 20"/><path d="M16 27v11M48 27v11" strokeWidth="5" strokeLinecap="round"/></g>}
    {style.accessory === 'star' && <path d="m45 16 1.3 3.1 3.3.2-2.6 2.1.8 3.2-2.8-1.8-2.8 1.8.8-3.2-2.6-2.1 3.3-.2Z" fill={style.detail}/>}
    {style.accessory === 'mask' && <path d="M19 35q13 7 26 0l-2 10q-11 5-22 0Z" fill={style.detail}/>}
    <path d="M0 58q17-6 31 6H0Z" fill={style.splash} opacity=".28"/>
  </svg>;
}
