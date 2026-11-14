import { useEffect, useRef, useState } from 'react';
import { BookOpen, Check, ChevronDown, LogOut, NotebookPen, Pencil, Shuffle, Sparkles, Wallet, X } from 'lucide-react';
import AvatarPortrait, { AVATAR_STYLES, avatarForAccount } from './AvatarPortrait';
import './ProfileMenu.css';

type Identity = { id: string; display_name: string };
type Preference = { name: string; color: string; avatar: number };
type Destination = 'positions' | 'journal' | 'learn';
type Props = {
  identity: Identity;
  onNavigate: (page: Destination) => void;
  onOpenGuide: () => void;
  onSignOut: () => void;
};

const colors = ['#89ddb0', '#87b9e6', '#d9aeef', '#efbf83', '#e9969a'];

function preferenceKey(id: string) { return `paperlane.profile.v1.${id}`; }
function readPreference(id: string): Preference {
  const fallback = { name: '', color: colors[0], avatar: avatarForAccount(id) };
  try {
    const parsed = JSON.parse(localStorage.getItem(preferenceKey(id)) || '{}') as Partial<Preference>;
    return { name: typeof parsed.name === 'string' ? parsed.name : '', color: colors.includes(parsed.color || '') ? parsed.color! : colors[0], avatar: Number.isInteger(parsed.avatar) && parsed.avatar! >= 0 && parsed.avatar! < AVATAR_STYLES.length ? parsed.avatar! : fallback.avatar };
  } catch { return fallback; }
}

export default function ProfileMenu({ identity, onNavigate, onOpenGuide, onSignOut }: Props) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [editing, setEditing] = useState(false);
  const [preference, setPreference] = useState<Preference>(() => readPreference(identity.id));
  const [draft, setDraft] = useState(preference);
  const root = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const name = preference.name.trim() || identity.display_name || 'My account';

  useEffect(() => { const next = readPreference(identity.id); setPreference(next); setDraft(next); setOpen(false); setPinned(false); setEditing(false); }, [identity.id]);
  useEffect(() => {
    if (!open) return;
    const dismiss = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) { setOpen(false); setPinned(false); setEditing(false); } };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpen(false); setPinned(false); setEditing(false); root.current?.querySelector<HTMLButtonElement>('.profile-trigger')?.focus(); } };
    document.addEventListener('pointerdown', dismiss);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', dismiss); document.removeEventListener('keydown', escape); };
  }, [open]);

  const close = () => { setOpen(false); setPinned(false); setEditing(false); };
  const navigate = (destination: Destination) => { close(); onNavigate(destination); };
  const save = (event: React.FormEvent) => {
    event.preventDefault();
    const next = { name: draft.name.trim().slice(0, 40), color: draft.color, avatar: draft.avatar };
    try { localStorage.setItem(preferenceKey(identity.id), JSON.stringify(next)); } catch { /* Browser storage may be unavailable. */ }
    setPreference(next);
    setDraft(next);
    setEditing(false);
  };
  const reset = () => {
    const next = { name: '', color: colors[0], avatar: avatarForAccount(identity.id) };
    try { localStorage.removeItem(preferenceKey(identity.id)); } catch { /* Browser storage may be unavailable. */ }
    setPreference(next);
    setDraft(next);
    setEditing(false);
  };

  return <div className="profile-control" ref={root} onMouseEnter={() => setOpen(true)} onMouseLeave={() => { if (!pinned && !editing) setOpen(false); }} onBlur={event => { if (!root.current?.contains(event.relatedTarget as Node) && !editing) { setOpen(false); setPinned(false); } }}>
    <button type="button" className={`profile-trigger${open ? ' active' : ''}`} aria-label={`Account menu for ${name}`} aria-haspopup="dialog" aria-expanded={open} aria-controls="paperlane-profile-menu" onClick={() => { if (pinned) close(); else { setOpen(true); setPinned(true); } }} onKeyDown={event => { if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true); setPinned(true); window.setTimeout(() => menu.current?.querySelector<HTMLButtonElement>('.profile-menu-item')?.focus(), 0); } }}>
      <span className="profile-avatar" style={{ '--avatar-color': preference.color } as React.CSSProperties} aria-hidden="true"><AvatarPortrait variant={preference.avatar}/></span>
      <span className="profile-trigger-name">{name}</span><ChevronDown size={14} aria-hidden="true"/>
    </button>
    {open && <div className="profile-popover" id="paperlane-profile-menu" role="dialog" aria-label="Account menu" ref={menu}>
      <div className="profile-popover-head"><span className="profile-avatar large" style={{ '--avatar-color': preference.color } as React.CSSProperties} aria-hidden="true"><AvatarPortrait variant={preference.avatar}/></span><div><strong>{name}</strong><small>Paper trading account</small></div></div>
      {editing ? <form className="profile-editor" onSubmit={save}>
        <div className="profile-editor-title"><strong>Personalise your profile</strong><button type="button" onClick={() => setEditing(false)} aria-label="Close profile editor"><X size={15}/></button></div>
        <label>Display name<input autoFocus type="text" value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} maxLength={40} placeholder={identity.display_name || 'Your name'}/></label>
        <fieldset><legend>Choose a character</legend><div className="profile-avatar-grid">{AVATAR_STYLES.map((style,index) => <button type="button" key={style.name} aria-label={`Choose ${style.name} avatar`} aria-pressed={draft.avatar === index} className={draft.avatar === index ? 'selected' : ''} onClick={() => setDraft({ ...draft, avatar: index })}><span><AvatarPortrait variant={index}/></span><small>{style.name}</small></button>)}</div><button type="button" className="profile-shuffle" onClick={() => setDraft({ ...draft, avatar: (draft.avatar + 1 + Math.floor(Math.random() * (AVATAR_STYLES.length - 1))) % AVATAR_STYLES.length })}><Shuffle size={14}/> Surprise me</button></fieldset>
        <fieldset><legend>Frame colour</legend><div className="profile-colors">{colors.map(color => <button type="button" key={color} aria-label={`Choose ${color} frame colour`} aria-pressed={draft.color === color} className={draft.color === color ? 'selected' : ''} style={{ backgroundColor: color }} onClick={() => setDraft({ ...draft, color })}>{draft.color === color && <Check size={14}/>}</button>)}</div></fieldset>
        <p>Saved on this browser. Your sign-in name stays the same.</p>
        <div className="profile-editor-actions"><button type="button" className="profile-reset" onClick={reset}>Reset</button><button type="submit" className="profile-save"><Check size={15}/> Save profile</button></div>
      </form> : <>
        <div className="profile-menu-section"><span>YOUR SPACE</span>
          <button type="button" className="profile-menu-item" onClick={() => navigate('positions')}><Wallet size={17}/> My positions</button>
          <button type="button" className="profile-menu-item" onClick={() => navigate('journal')}><NotebookPen size={17}/> Trading journal</button>
          <button type="button" className="profile-menu-item" onClick={() => navigate('learn')}><BookOpen size={17}/> Learning library</button>
        </div>
        <div className="profile-menu-section"><span>PERSONALISE</span>
          <button type="button" className="profile-menu-item" onClick={() => { setDraft(preference); setEditing(true); }}><Pencil size={17}/> Edit profile</button>
          <button type="button" className="profile-menu-item" onClick={() => { close(); onOpenGuide(); }}><Sparkles size={17}/> Guided practice</button>
        </div>
        <button type="button" className="profile-menu-item profile-logout" onClick={() => { close(); onSignOut(); }}><LogOut size={17}/> Sign out</button>
      </>}
    </div>}
  </div>;
}
