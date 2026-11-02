#!/usr/bin/env python3
"""Render a deterministic glyph specimen from bundled files (not a Godot capture)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, features

ROOT = Path(__file__).resolve().parents[1]
NAVY, PANEL, EDGE = '#0b122a', '#121f40', '#2e4777'
WHITE, GOLD, MUTED = '#edf5ff', '#ffce42', '#9eafd1'

def face(name, size, index=0):
    return ImageFont.truetype(str(ROOT / name), size, index=index)


def main():
    if not features.check('raqm'):
        raise SystemExit('This multilingual specimen requires Pillow with RAQM shaping')
    im = Image.new('RGB', (1200, 940), NAVY)
    d = ImageDraw.Draw(im)
    small = face('fallbacks/NotoSans-Regular.ttf', 16)
    note = face('fallbacks/NotoSans-Regular.ttf', 14)
    arcade = face('dist/NeptuneBubble.ttf', 48)
    d.rectangle((36, 34, 1164, 39), fill=GOLD)
    d.text((40, 62), 'NEPTUNE BUBBLE', font=arcade, fill=GOLD, stroke_width=0)
    d.text((42, 122), 'Saturn Bomberman-inspired bubble lettering / original outlines + multilingual fallbacks', font=small, fill=MUTED)
    d.rounded_rectangle((36, 164, 1164, 365), radius=8, fill=PANEL, outline=EDGE, width=2)
    d.text((58, 182), 'ROUNDED BUBBLE DISPLAY  /  SCALABLE OUTLINES', font=small, fill=MUTED)
    for y, text, size, color in [(220,'BATTLE START!  1P  2P  0123456789',24,GOLD),
                                (266,'ABCDEFGHIJKLMNOPQRSTUVWXYZ',24,WHITE),
                                (308,'abcdefghijklmnopqrstuvwxyz  ÀÉÖçñü',24,WHITE)]:
        d.text((58,y),text,font=face('dist/NeptuneBubble.ttf',size),fill=color,stroke_width=1,stroke_fill='#050a18')
    cards = [
        ('JAPANESE / JP', 'ボンバーマン　対戦開始！', 'NotoSansCJK-Bold.ttc',0,'ltr'),
        ('CHINESE / SIMPLIFIED', '炸弹人　开始游戏！', 'NotoSansCJK-Bold.ttc',2,'ltr'),
        ('CHINESE / TRADITIONAL', '炸彈人　開始遊戲！', 'NotoSansCJK-Bold.ttc',3,'ltr'),
        ('KOREAN / KR', '봄버맨　게임 시작!', 'NotoSansCJK-Bold.ttc',1,'ltr'),
        ('ARABIC / RIGHT TO LEFT', 'ابدأ اللعب الآن', 'NotoSansArabic-Regular.ttf',0,'rtl'),
        ('HEBREW / RIGHT TO LEFT', 'המשחק מתחיל עכשיו', 'NotoSansHebrew-Regular.ttf',0,'rtl'),
        ('HINDI / DEVANAGARI', 'खेल शुरू करें', 'NotoSansDevanagari-Regular.ttf',0,'ltr'),
        ('THAI', 'เริ่มเกมได้เลย', 'NotoSansThai-Regular.ttf',0,'ltr'),
    ]
    for i,(label,text,name,index,direction) in enumerate(cards):
        x,y=36+(i%2)*578,390+(i//2)*112
        d.rounded_rectangle((x,y,x+550,y+98),radius=6,fill=PANEL,outline=EDGE,width=1)
        d.text((x+20,y+12),label,font=note,fill=MUTED)
        font=face('fallbacks/'+name,28,index)
        if direction=='rtl':
            d.text((x+528,y+57),text,font=font,fill=WHITE,anchor='rm',direction='rtl')
        else:
            d.text((x+20,y+42),text,font=font,fill=WHITE,direction=direction)
    d.text((40,864),'Bundled glyph specimen. Fallback scripts retain Noto outlines; not every Unicode character is covered.',font=note,fill=MUTED)
    d.text((40,890),'SIL OFL 1.1  /  Godot 4 resources  /  Optional pixel HUD face  /  Regional CJK glyph forms',font=note,fill=MUTED)
    target=ROOT/'preview.png'
    im.save(target,optimize=False)
    print(target)

if __name__=='__main__':
    main()
