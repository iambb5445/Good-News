#!/usr/bin/env python3
"""
Random Character Generator

Generates a randomly assembled character from modular PNG assets.
"""

import random
from pathlib import Path
from PIL import Image

# Base path to assets
ASSETS_PATH = Path(__file__).parent / "modular-characters" / "PNG"

# Canvas dimensions
CANVAS_WIDTH = 450
CANVAS_HEIGHT = 580

# Asset options
SKIN_TINTS = list(range(1, 9))  # 1-8

SHIRT_COLORS = ["Blue", "Green", "Grey", "Navy", "Pine", "Red", "White", "Yellow"]
SHIRT_STYLES = list(range(1, 9))  # 1-8
SLEEVE_LENGTHS = ["long", "short", "shorter"]

PANTS_COLORS = ["Blue 1", "Blue 2", "Brown", "Green", "Grey", "Light Blue",
                "Navy", "Pine", "Red", "Tan", "White", "Yellow"]
PANTS_STYLES = list(range(1, 5))  # 1-4
LEG_LENGTHS = ["long", "short", "shorter"]

SHOE_COLORS = ["Black", "Blue", "Brown 1", "Brown 2", "Grey", "Red", "Tan"]
SHOE_STYLES = list(range(1, 6))  # 1-5

HAIR_COLORS = ["Black", "Blonde", "Brown 1", "Brown 2", "Grey", "Red", "Tan", "White"]
HAIR_GENDERS = ["Man", "Woman"]
HAIR_STYLES_MAN = list(range(1, 9))  # 1-8
HAIR_STYLES_WOMAN = list(range(1, 7))  # 1-6

EYE_COLORS = ["Black", "Blue", "Brown", "Green", "Pine"]
EYE_SIZES = ["large", "small"]

# Map hair color folder names to eyebrow prefix
EYEBROW_COLOR_MAP = {
    "Black": "black",
    "Blonde": "blonde",
    "Brown 1": "brown1",
    "Brown 2": "brown2",
    "Grey": "grey",
    "Red": "red",
    "Tan": "tan",
    "White": "white"
}
EYEBROW_STYLES = list(range(1, 4))  # 1-3

MOUTH_EXPRESSIONS = ["glad", "happy", "oh", "sad", "straight", "teethLower", "teethUpper"]

NOSE_STYLES = list(range(1, 4))  # 1-3


def get_skin_path(tint: int, part: str) -> Path:
    """Get path to skin asset. part: arm, hand, head, leg, neck"""
    return ASSETS_PATH / "Skin" / f"Tint {tint}" / f"tint{tint}_{part}.png"


def get_shirt_path(color: str, style: int) -> Path:
    """Get path to shirt body asset."""
    # Handle naming inconsistency: Blue uses blueShirt1, Yellow uses shirtYellow1
    if color == "Blue":
        return ASSETS_PATH / "Shirts" / color / f"blueShirt{style}.png"
    else:
        # Most colors use colorShirt or shirtColor - check what exists
        color_lower = color.lower()
        path1 = ASSETS_PATH / "Shirts" / color / f"{color_lower}Shirt{style}.png"
        path2 = ASSETS_PATH / "Shirts" / color / f"shirt{color}{style}.png"
        if path1.exists():
            return path1
        return path2


def get_sleeve_path(color: str, length: str) -> Path:
    """Get path to sleeve asset."""
    # Handle naming inconsistency: Blue uses blueArm_long, Yellow uses armYellow_long
    color_lower = color.lower()
    path1 = ASSETS_PATH / "Shirts" / color / f"{color_lower}Arm_{length}.png"
    path2 = ASSETS_PATH / "Shirts" / color / f"arm{color}_{length}.png"
    if path1.exists():
        return path1
    return path2


def get_pants_body_path(color: str, style: int) -> Path:
    """Get path to pants body asset."""
    # Map folder name to file prefix
    color_map = {
        "Blue 1": "Blue1",
        "Blue 2": "Blue2",
        "Light Blue": "LightBlue",
    }
    file_color = color_map.get(color, color)
    return ASSETS_PATH / "Pants" / color / f"pants{file_color}{style}.png"


def get_pant_leg_path(color: str, length: str) -> Path:
    """Get path to pant leg asset."""
    # Handle naming inconsistency
    color_map = {
        "Blue 1": "Blue1",
        "Blue 2": "Blue2",
        "Light Blue": "LightBlue",
    }
    file_color = color_map.get(color, color)

    # Some colors use pantsColor_long, others use legColor_long
    path1 = ASSETS_PATH / "Pants" / color / f"pants{file_color}_{length}.png"
    path2 = ASSETS_PATH / "Pants" / color / f"leg{file_color}_{length}.png"
    if path1.exists():
        return path1
    return path2


def get_shoe_path(color: str, style: int) -> Path:
    """Get path to shoe asset."""
    color_map = {
        "Brown 1": "brown1",
        "Brown 2": "brown2",
    }
    file_color = color_map.get(color, color.lower())
    return ASSETS_PATH / "Shoes" / color / f"{file_color}Shoe{style}.png"


def get_hair_path(color: str, gender: str, style: int) -> Path:
    """Get path to hair asset."""
    color_map = {
        "Brown 1": "brown1",
        "Brown 2": "brown2",
    }
    file_color = color_map.get(color, color.lower())
    return ASSETS_PATH / "Hair" / color / f"{file_color}{gender}{style}.png"


def get_eye_path(color: str, size: str) -> Path:
    """Get path to eye asset."""
    return ASSETS_PATH / "Face" / "Eyes" / f"eye{color}_{size}.png"


def get_eyebrow_path(color: str, style: int) -> Path:
    """Get path to eyebrow asset. color is hair color folder name."""
    brow_color = EYEBROW_COLOR_MAP[color]
    return ASSETS_PATH / "Face" / "Eyebrows" / f"{brow_color}Brow{style}.png"


def get_mouth_path(expression: str) -> Path:
    """Get path to mouth asset."""
    return ASSETS_PATH / "Face" / "Mouth" / f"mouth_{expression}.png"


def get_nose_path(tint: int, style: int) -> Path:
    """Get path to nose asset. tint must match skin tint."""
    return ASSETS_PATH / "Face" / "Nose" / f"Tint {tint}" / f"tint{tint}Nose{style}.png"


def random_character_config() -> dict:
    """Generate random selections for all character properties."""
    skin_tint = random.choice(SKIN_TINTS)
    hair_color = random.choice(HAIR_COLORS)
    hair_gender = random.choice(HAIR_GENDERS)

    if hair_gender == "Man":
        hair_style = random.choice(HAIR_STYLES_MAN)
    else:
        hair_style = random.choice(HAIR_STYLES_WOMAN)

    return {
        "skin_tint": skin_tint,
        "shirt_color": random.choice(SHIRT_COLORS),
        "shirt_style": random.choice(SHIRT_STYLES),
        "sleeve_length": random.choice(SLEEVE_LENGTHS),
        "pants_color": random.choice(PANTS_COLORS),
        "pants_style": random.choice(PANTS_STYLES),
        "leg_length": random.choice(LEG_LENGTHS),
        "shoe_color": random.choice(SHOE_COLORS),
        "shoe_style": random.choice(SHOE_STYLES),
        "hair_color": hair_color,
        "hair_gender": hair_gender,
        "hair_style": hair_style,
        "eye_color": random.choice(EYE_COLORS),
        "eye_size": random.choice(EYE_SIZES),
        "eyebrow_style": random.choice(EYEBROW_STYLES),
        "mouth_expression": random.choice(MOUTH_EXPRESSIONS),
        "nose_style": random.choice(NOSE_STYLES),
    }


def paste_image(canvas: Image.Image, asset_path: Path, position: tuple, flip_horizontal: bool = False):
    """Paste an image onto the canvas at the given position with alpha compositing."""
    if not asset_path.exists():
        print(f"Warning: Asset not found: {asset_path}")
        return

    img = Image.open(asset_path).convert("RGBA")

    if flip_horizontal:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)

    # Use alpha composite to handle transparency properly
    # Create a temporary image at canvas size with the asset positioned
    temp = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    temp.paste(img, position)

    # Composite onto canvas
    return Image.alpha_composite(canvas, temp)


def render_character(config: dict) -> Image.Image:
    """Render the character based on the configuration."""
    canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))

    # Central reference points
    center_x = CANVAS_WIDTH // 2

    # Vertical positioning (top-down approach)
    # Hair top ~ 20, head below hair, neck below head, shirt below neck, etc.

    # Key vertical positions (approximate, centered on canvas)
    head_top = 30
    neck_top = head_top + 145  # Head is 168 tall, but neck overlaps
    shirt_top = neck_top + 20   # Neck is 37 tall, overlap with shirt
    pants_top = shirt_top + 165  # Shirt is 174 tall, pants at bottom
    legs_top = pants_top + 35   # Pants body is 47 tall, legs below
    shoes_top = legs_top + 125  # Legs are ~164 tall, shoes at bottom

    # Calculate horizontal positions
    head_x = center_x - 173 // 2  # Head is 173 wide
    neck_x = center_x - 96 // 2   # Neck is 96 wide
    shirt_x = center_x - 153 // 2  # Shirt is 153 wide
    pants_x = center_x - 153 // 2  # Pants body is 153 wide

    # Arms/sleeves positioned at sides of shirt
    # Arm is 170 wide, positioned so it extends from shoulder
    right_arm_x = shirt_x + 153 - 25  # Right side, slight overlap
    left_arm_x = shirt_x - 170 + 25   # Left side, slight overlap
    arm_y = shirt_top - 5  # Slightly above shirt top

    # Legs positioned under pants
    # Legs are ~93-111 wide depending on type
    leg_spacing = 50
    right_leg_x = center_x + 5
    left_leg_x = center_x - 93 - 5

    # Shoes at bottom of legs
    shoe_spacing = 50
    right_shoe_x = center_x + 10
    left_shoe_x = center_x - 94 - 10

    # Face features positioned on head
    face_center_x = head_x + 173 // 2
    face_center_y = head_top + 168 // 2

    # Eye positions (eyes are 21x21)
    eye_y = face_center_y - 15
    right_eye_x = face_center_x + 15
    left_eye_x = face_center_x - 15 - 21

    # Eyebrow positions (above eyes, eyebrows are 40x17)
    eyebrow_y = eye_y - 20
    right_eyebrow_x = face_center_x + 10
    left_eyebrow_x = face_center_x - 10 - 40

    # Nose position (center, below eyes, nose is 31x21)
    nose_x = face_center_x - 31 // 2
    nose_y = eye_y + 25

    # Mouth position (center, below nose, mouth is 34x13)
    mouth_x = face_center_x - 34 // 2
    mouth_y = nose_y + 25

    # Hair position (on top of head)
    hair_x = head_x + 173 // 2 - 158 // 2  # Center hair (158 wide) on head
    hair_y = head_top - 10  # Hair extends above head

    # Determine if we need exposed skin
    needs_skin_arms = config["sleeve_length"] in ["short", "shorter"]
    needs_skin_legs = config["leg_length"] in ["short", "shorter"]

    # Drawing order (per requirements.md):
    # 1. Skin elements (neck, head, arms if exposed, legs if exposed)
    # 2. Hands, sleeves, pant legs
    # 3. Pants body
    # 4. Shirt body
    # 5. Shoes
    # 6. Facial features (mouth, nose, eyes, eyebrows)
    # 7. Hair (topmost)

    tint = config["skin_tint"]

    # 1. Skin elements
    # Neck
    canvas = paste_image(canvas, get_skin_path(tint, "neck"), (neck_x, neck_top))

    # Head
    canvas = paste_image(canvas, get_skin_path(tint, "head"), (head_x, head_top))

    # Skin arms (if needed for short/shorter sleeves)
    if needs_skin_arms:
        canvas = paste_image(canvas, get_skin_path(tint, "arm"), (right_arm_x, arm_y))
        canvas = paste_image(canvas, get_skin_path(tint, "arm"), (left_arm_x, arm_y), flip_horizontal=True)

    # Skin legs (if needed for short/shorter pants)
    if needs_skin_legs:
        canvas = paste_image(canvas, get_skin_path(tint, "leg"), (right_leg_x, legs_top))
        canvas = paste_image(canvas, get_skin_path(tint, "leg"), (left_leg_x, legs_top), flip_horizontal=True)

    # 2. Hands, sleeves, pant legs
    # Hands (at end of arms)
    hand_offset_x = 130  # How far along the arm the hand appears
    hand_offset_y = 90
    canvas = paste_image(canvas, get_skin_path(tint, "hand"),
                        (right_arm_x + hand_offset_x, arm_y + hand_offset_y))
    canvas = paste_image(canvas, get_skin_path(tint, "hand"),
                        (left_arm_x + 170 - 61 - hand_offset_x, arm_y + hand_offset_y),
                        flip_horizontal=True)

    # Sleeves
    sleeve_path = get_sleeve_path(config["shirt_color"], config["sleeve_length"])
    canvas = paste_image(canvas, sleeve_path, (right_arm_x, arm_y))
    canvas = paste_image(canvas, sleeve_path, (left_arm_x, arm_y), flip_horizontal=True)

    # Pant legs
    pant_leg_path = get_pant_leg_path(config["pants_color"], config["leg_length"])
    canvas = paste_image(canvas, pant_leg_path, (right_leg_x, legs_top))
    canvas = paste_image(canvas, pant_leg_path, (left_leg_x, legs_top), flip_horizontal=True)

    # 3. Pants body
    pants_path = get_pants_body_path(config["pants_color"], config["pants_style"])
    canvas = paste_image(canvas, pants_path, (pants_x, pants_top))

    # 4. Shirt body
    shirt_path = get_shirt_path(config["shirt_color"], config["shirt_style"])
    canvas = paste_image(canvas, shirt_path, (shirt_x, shirt_top))

    # 5. Shoes
    shoe_path = get_shoe_path(config["shoe_color"], config["shoe_style"])
    canvas = paste_image(canvas, shoe_path, (right_shoe_x, shoes_top))
    canvas = paste_image(canvas, shoe_path, (left_shoe_x, shoes_top), flip_horizontal=True)

    # 6. Facial features
    # Mouth
    mouth_path = get_mouth_path(config["mouth_expression"])
    canvas = paste_image(canvas, mouth_path, (mouth_x, mouth_y))

    # Nose (must match skin tint)
    nose_path = get_nose_path(tint, config["nose_style"])
    canvas = paste_image(canvas, nose_path, (nose_x, nose_y))

    # Eyes
    eye_path = get_eye_path(config["eye_color"], config["eye_size"])
    canvas = paste_image(canvas, eye_path, (right_eye_x, eye_y))
    canvas = paste_image(canvas, eye_path, (left_eye_x, eye_y))

    # Eyebrows (use hair color for eyebrow color, must be mirrored)
    eyebrow_path = get_eyebrow_path(config["hair_color"], config["eyebrow_style"])
    canvas = paste_image(canvas, eyebrow_path, (right_eyebrow_x, eyebrow_y))
    canvas = paste_image(canvas, eyebrow_path, (left_eyebrow_x, eyebrow_y), flip_horizontal=True)

    # 7. Hair (topmost)
    hair_path = get_hair_path(config["hair_color"], config["hair_gender"], config["hair_style"])
    canvas = paste_image(canvas, hair_path, (hair_x, hair_y))

    return canvas


def main():
    """Generate and display a random character."""
    config = random_character_config()

    print("Generated character with:")
    for key, value in config.items():
        print(f"  {key}: {value}")

    image = render_character(config)

    # Save the image
    output_path = Path(__file__).parent / "character.png"
    image.save(output_path)
    print(f"\nSaved to: {output_path}")

    # Display with matplotlib
    try:
        import matplotlib.pyplot as plt
        plt.figure(figsize=(8, 10))
        plt.imshow(image)
        plt.axis('off')
        plt.title("Random Character")
        plt.tight_layout()
        plt.show()
    except ImportError:
        print("matplotlib not available, skipping display")


if __name__ == "__main__":
    main()
