"""Render the OpenShorts watermark lockup (white mark + wordmark) to a PNG.

Pre-rendered at 4x so it downscales cleanly onto any clip size, with a soft
dark shadow so it stays legible over bright footage.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter

S = 4                      # supersampling
H = 64 * S                 # lockup height
PAD = 6 * S

font = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", int(38 * S), index=1)  # Bold
text = "OpenShorts"

tmp = Image.new("RGBA", (10, 10))
tb = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
tw, th = tb[2] - tb[0], tb[3] - tb[1]

mark = int(40 * S)         # square mark
gap = int(12 * S)
W = mark + gap + tw + PAD * 2

img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Rounded square outline + play triangle: reads as "clip/play" at small sizes.
mx, my = PAD, (H - mark) // 2
r = int(mark * 0.28)
d.rounded_rectangle([mx, my, mx + mark, my + mark], radius=r,
                    outline=(255, 255, 255, 255), width=int(3.5 * S))
t = mark * 0.30
cx, cy = mx + mark / 2, my + mark / 2
d.polygon([(cx - t * 0.55, cy - t), (cx - t * 0.55, cy + t), (cx + t * 0.85, cy)],
          fill=(255, 255, 255, 255))

d.text((mx + mark + gap - tb[0], (H - th) // 2 - tb[1]), text, font=font,
       fill=(255, 255, 255, 255))

# Soft shadow behind everything for contrast on light footage.
shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
shadow.paste((0, 0, 0, 170), (0, 0), img.split()[3])
shadow = shadow.filter(ImageFilter.GaussianBlur(int(2.5 * S)))
out = Image.alpha_composite(shadow, img)

out.save("watermark.png")
print("watermark.png", out.size)
