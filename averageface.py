#!/usr/bin/env python3
"""
AverageFace - Quantum Character Generator

Visualizes characters as quantum-like superpositions. Unspecified properties
are shown as pixel-averaged composites of all possibilities. When the user
fixes a property, only matching possibilities are averaged.
"""

import random
from pathlib import Path
from typing import Optional
from PIL import Image
import numpy as np

# Base path to assets
ASSETS_PATH = Path(__file__).parent / "modular-characters" / "PNG"

# Canvas dimensions
CANVAS_WIDTH = 450
CANVAS_HEIGHT = 580


# =============================================================================
# Asset Discovery
# =============================================================================

def discover_assets() -> dict:
    """Scan directories and build lookup dictionaries for all assets."""
    assets = {
        "skin_tints": [],
        "shirt_colors": [],
        "shirt_styles": [],
        "sleeve_lengths": ["long", "short", "shorter"],
        "pants_colors": [],
        "pants_styles": [],
        "leg_lengths": ["long", "short", "shorter"],
        "shoe_colors": [],
        "shoe_styles": [],
        "hair_colors": [],
        "hair_genders": ["Man", "Woman"],
        "hair_styles_man": [],
        "hair_styles_woman": [],
        "eye_colors": [],
        "eye_sizes": ["large", "small"],
        "eyebrow_styles": [],
        "mouth_expressions": [],
        "nose_styles": [],
    }

    # Skin tints
    skin_path = ASSETS_PATH / "Skin"
    for d in sorted(skin_path.iterdir()):
        if d.is_dir() and d.name.startswith("Tint"):
            tint_num = int(d.name.split()[-1])
            assets["skin_tints"].append(tint_num)

    # Shirts
    shirts_path = ASSETS_PATH / "Shirts"
    for d in sorted(shirts_path.iterdir()):
        if d.is_dir():
            assets["shirt_colors"].append(d.name)
    # Shirt styles (1-8)
    assets["shirt_styles"] = list(range(1, 9))

    # Pants
    pants_path = ASSETS_PATH / "Pants"
    for d in sorted(pants_path.iterdir()):
        if d.is_dir():
            assets["pants_colors"].append(d.name)
    # Pants styles (1-4)
    assets["pants_styles"] = list(range(1, 5))

    # Shoes
    shoes_path = ASSETS_PATH / "Shoes"
    for d in sorted(shoes_path.iterdir()):
        if d.is_dir():
            assets["shoe_colors"].append(d.name)
    # Shoe styles (1-5)
    assets["shoe_styles"] = list(range(1, 6))

    # Hair
    hair_path = ASSETS_PATH / "Hair"
    for d in sorted(hair_path.iterdir()):
        if d.is_dir():
            assets["hair_colors"].append(d.name)
    # Hair styles vary by gender - scan first color dir to find them
    if assets["hair_colors"]:
        first_color = assets["hair_colors"][0]
        hair_dir = hair_path / first_color
        for f in hair_dir.iterdir():
            if "Man" in f.name:
                style = int(f.stem[-1])
                if style not in assets["hair_styles_man"]:
                    assets["hair_styles_man"].append(style)
            elif "Woman" in f.name:
                style = int(f.stem[-1])
                if style not in assets["hair_styles_woman"]:
                    assets["hair_styles_woman"].append(style)
        assets["hair_styles_man"].sort()
        assets["hair_styles_woman"].sort()

    # Eyes
    eyes_path = ASSETS_PATH / "Face" / "Eyes"
    eye_colors_found = set()
    for f in eyes_path.iterdir():
        if f.suffix == ".png":
            # eyeBlack_large.png -> Black
            parts = f.stem.split("_")
            color = parts[0].replace("eye", "")
            eye_colors_found.add(color)
    assets["eye_colors"] = sorted(eye_colors_found)

    # Eyebrows
    eyebrows_path = ASSETS_PATH / "Face" / "Eyebrows"
    brow_styles = set()
    for f in eyebrows_path.iterdir():
        if f.suffix == ".png":
            # blackBrow1.png -> 1
            style = int(f.stem[-1])
            brow_styles.add(style)
    assets["eyebrow_styles"] = sorted(brow_styles)

    # Mouth
    mouth_path = ASSETS_PATH / "Face" / "Mouth"
    for f in sorted(mouth_path.iterdir()):
        if f.suffix == ".png":
            # mouth_happy.png -> happy
            expr = f.stem.replace("mouth_", "")
            assets["mouth_expressions"].append(expr)

    # Nose
    nose_path = ASSETS_PATH / "Face" / "Nose" / "Tint 1"
    for f in nose_path.iterdir():
        if f.suffix == ".png":
            # tint1Nose1.png -> 1
            style = int(f.stem[-1])
            if style not in assets["nose_styles"]:
                assets["nose_styles"].append(style)
    assets["nose_styles"].sort()

    return assets


# Global assets cache
ASSETS = None

def get_assets() -> dict:
    """Get or initialize the assets dictionary."""
    global ASSETS
    if ASSETS is None:
        ASSETS = discover_assets()
    return ASSETS


# =============================================================================
# Asset Path Resolution
# =============================================================================

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


def get_skin_path(tint: int, part: str) -> Path:
    """Get path to skin asset. part: arm, hand, head, leg, neck"""
    return ASSETS_PATH / "Skin" / f"Tint {tint}" / f"tint{tint}_{part}.png"


def get_shirt_path(color: str, style: int) -> Path:
    """Get path to shirt body asset."""
    if color == "Blue":
        return ASSETS_PATH / "Shirts" / color / f"blueShirt{style}.png"
    else:
        color_lower = color.lower()
        path1 = ASSETS_PATH / "Shirts" / color / f"{color_lower}Shirt{style}.png"
        path2 = ASSETS_PATH / "Shirts" / color / f"shirt{color}{style}.png"
        if path1.exists():
            return path1
        return path2


def get_sleeve_path(color: str, length: str) -> Path:
    """Get path to sleeve asset."""
    color_lower = color.lower()
    path1 = ASSETS_PATH / "Shirts" / color / f"{color_lower}Arm_{length}.png"
    path2 = ASSETS_PATH / "Shirts" / color / f"arm{color}_{length}.png"
    if path1.exists():
        return path1
    return path2


def get_pants_body_path(color: str, style: int) -> Path:
    """Get path to pants body asset."""
    color_map = {
        "Blue 1": "Blue1",
        "Blue 2": "Blue2",
        "Light Blue": "LightBlue",
    }
    file_color = color_map.get(color, color)
    return ASSETS_PATH / "Pants" / color / f"pants{file_color}{style}.png"


def get_pant_leg_path(color: str, length: str) -> Path:
    """Get path to pant leg asset."""
    color_map = {
        "Blue 1": "Blue1",
        "Blue 2": "Blue2",
        "Light Blue": "LightBlue",
    }
    file_color = color_map.get(color, color)
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


def get_eyebrow_path(hair_color: str, style: int) -> Path:
    """Get path to eyebrow asset."""
    brow_color = EYEBROW_COLOR_MAP[hair_color]
    return ASSETS_PATH / "Face" / "Eyebrows" / f"{brow_color}Brow{style}.png"


def get_mouth_path(expression: str) -> Path:
    """Get path to mouth asset."""
    return ASSETS_PATH / "Face" / "Mouth" / f"mouth_{expression}.png"


def get_nose_path(tint: int, style: int) -> Path:
    """Get path to nose asset."""
    return ASSETS_PATH / "Face" / "Nose" / f"Tint {tint}" / f"tint{tint}Nose{style}.png"


# =============================================================================
# Character Model
# =============================================================================

class CharacterState:
    """Tracks which properties are fixed vs. free (superposed)."""

    # Property definitions: (name, display_name, options_key)
    PROPERTIES = [
        ("skin_tint", "Skin Tint", "skin_tints"),
        ("shirt_color", "Shirt Color", "shirt_colors"),
        ("shirt_style", "Shirt Style", "shirt_styles"),
        ("sleeve_length", "Sleeve Length", "sleeve_lengths"),
        ("pants_color", "Pants Color", "pants_colors"),
        ("pants_style", "Pants Style", "pants_styles"),
        ("leg_length", "Leg Length", "leg_lengths"),
        ("shoe_color", "Shoe Color", "shoe_colors"),
        ("shoe_style", "Shoe Style", "shoe_styles"),
        ("hair_color", "Hair Color", "hair_colors"),
        ("hair_gender", "Hair Gender", "hair_genders"),
        ("hair_style", "Hair Style", None),  # Depends on gender
        ("eye_color", "Eye Color", "eye_colors"),
        ("eye_size", "Eye Size", "eye_sizes"),
        ("eyebrow_style", "Eyebrow Style", "eyebrow_styles"),
        ("mouth_expression", "Mouth", "mouth_expressions"),
        ("nose_style", "Nose Style", "nose_styles"),
    ]

    def __init__(self):
        self.fixed = {}  # property_name -> value
        self.assets = get_assets()

    def fix(self, prop: str, value):
        """Fix a property to a specific value."""
        self.fixed[prop] = value

    def unfix(self, prop: str):
        """Remove a fixed constraint."""
        if prop in self.fixed:
            del self.fixed[prop]

    def is_fixed(self, prop: str) -> bool:
        """Check if a property is fixed."""
        return prop in self.fixed

    def get_fixed(self, prop: str):
        """Get the fixed value for a property, or None if not fixed."""
        return self.fixed.get(prop)

    def get_options(self, prop: str) -> list:
        """Get available options for a property."""
        if prop == "hair_style":
            # Depends on hair_gender
            if self.is_fixed("hair_gender"):
                gender = self.fixed["hair_gender"]
                if gender == "Man":
                    return self.assets["hair_styles_man"]
                else:
                    return self.assets["hair_styles_woman"]
            else:
                # Return union of both
                return list(set(self.assets["hair_styles_man"]) |
                           set(self.assets["hair_styles_woman"]))

        for name, _, options_key in self.PROPERTIES:
            if name == prop and options_key:
                return self.assets[options_key]
        return []

    def reset(self):
        """Clear all fixed properties."""
        self.fixed.clear()

    def generate_all_configs(self) -> list:
        """Generate all possible character configurations given current constraints."""
        configs = [{}]

        for prop, _, _ in self.PROPERTIES:
            if self.is_fixed(prop):
                # Use fixed value
                for config in configs:
                    config[prop] = self.fixed[prop]
            else:
                # Expand with all options
                options = self.get_options(prop)
                new_configs = []
                for config in configs:
                    for opt in options:
                        new_config = config.copy()
                        new_config[prop] = opt
                        new_configs.append(new_config)
                configs = new_configs

        # Filter out invalid hair_style combinations
        valid_configs = []
        for config in configs:
            gender = config.get("hair_gender", "Man")
            style = config.get("hair_style", 1)
            if gender == "Man":
                valid_styles = self.assets["hair_styles_man"]
            else:
                valid_styles = self.assets["hair_styles_woman"]
            if style in valid_styles:
                valid_configs.append(config)

        return valid_configs

    def sample_config(self) -> dict:
        """Generate a single random configuration respecting constraints."""
        config = {}
        for prop, _, _ in self.PROPERTIES:
            if self.is_fixed(prop):
                config[prop] = self.fixed[prop]
            else:
                options = self.get_options(prop)
                if prop == "hair_style" and "hair_gender" in config:
                    # Use gender-appropriate styles
                    if config["hair_gender"] == "Man":
                        options = self.assets["hair_styles_man"]
                    else:
                        options = self.assets["hair_styles_woman"]
                config[prop] = random.choice(options)
        return config


# =============================================================================
# Rendering
# =============================================================================

def load_image(path: Path) -> Optional[np.ndarray]:
    """Load an image as RGBA numpy array."""
    if not path.exists():
        return None
    img = Image.open(path).convert("RGBA")
    return np.array(img, dtype=np.float32)


def paste_onto_canvas(canvas: np.ndarray, img: np.ndarray, position: tuple,
                      flip_horizontal: bool = False):
    """Paste an image onto a canvas with alpha blending."""
    if flip_horizontal:
        img = np.fliplr(img)

    x, y = position
    h, w = img.shape[:2]
    ch, cw = canvas.shape[:2]

    # Calculate valid region
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(cw, x + w), min(ch, y + h)

    if x1 >= x2 or y1 >= y2:
        return

    # Source region
    sx1 = x1 - x
    sy1 = y1 - y
    sx2 = sx1 + (x2 - x1)
    sy2 = sy1 + (y2 - y1)

    # Alpha blending
    src = img[sy1:sy2, sx1:sx2]
    dst = canvas[y1:y2, x1:x2]

    src_alpha = src[:, :, 3:4] / 255.0
    dst_alpha = dst[:, :, 3:4] / 255.0

    out_alpha = src_alpha + dst_alpha * (1 - src_alpha)
    out_alpha_safe = np.where(out_alpha > 0, out_alpha, 1)

    out_rgb = (src[:, :, :3] * src_alpha +
               dst[:, :, :3] * dst_alpha * (1 - src_alpha)) / out_alpha_safe

    canvas[y1:y2, x1:x2, :3] = out_rgb
    canvas[y1:y2, x1:x2, 3:4] = out_alpha * 255


def get_positions() -> dict:
    """Calculate all positioning constants."""
    center_x = CANVAS_WIDTH // 2

    head_top = 0  
    neck_top = head_top + 145
    shirt_top = neck_top + 10
    pants_top = shirt_top + 165
    legs_top = pants_top + 15 
    shoes_top = legs_top + 125

    head_x = center_x - 173 // 2
    neck_x = center_x - 96 // 2
    shirt_x = center_x - 153 // 2
    pants_x = center_x - 153 // 2

    right_arm_x = shirt_x + 153 - 25
    left_arm_x = shirt_x - 170 + 25
    arm_y = shirt_top - 5

    right_leg_x = center_x  # Shifted left 5px for alignment
    left_leg_x = center_x - 93 - 10  # Shifted left 5px for alignment

    right_shoe_x = center_x + 35  # Moved outward 5px
    left_shoe_x = center_x - 135  # Moved outward 5px

    face_center_x = head_x + 173 // 2
    face_center_y = head_top + 168 // 2

    eye_y = face_center_y - 15
    right_eye_x = face_center_x + 15
    left_eye_x = face_center_x - 15 - 21

    eyebrow_y = eye_y - 20
    right_eyebrow_x = face_center_x + 10
    left_eyebrow_x = face_center_x - 10 - 40

    nose_x = face_center_x - 31 // 2
    nose_y = eye_y + 20

    mouth_x = face_center_x - 34 // 2
    mouth_y = nose_y + 35

    hair_x = head_x + 173 // 2 - 158 // 2
    hair_y = head_top - 10

    hand_offset_x = 130
    hand_offset_y = 90

    return {
        "head": (head_x, head_top),
        "neck": (neck_x, neck_top),
        "shirt": (shirt_x, shirt_top),
        "pants": (pants_x, pants_top),
        "right_arm": (right_arm_x, arm_y),
        "left_arm": (left_arm_x, arm_y),
        "right_leg": (right_leg_x, legs_top),
        "left_leg": (left_leg_x, legs_top),
        "right_shoe": (right_shoe_x, shoes_top),
        "left_shoe": (left_shoe_x, shoes_top),
        "right_eye": (right_eye_x, eye_y),
        "left_eye": (left_eye_x, eye_y),
        "right_eyebrow": (right_eyebrow_x, eyebrow_y),
        "left_eyebrow": (left_eyebrow_x, eyebrow_y),
        "nose": (nose_x, nose_y),
        "mouth": (mouth_x, mouth_y),
        "hair": (hair_x, hair_y),
        "right_hand": (right_arm_x + hand_offset_x, arm_y + hand_offset_y),
        "left_hand": (left_arm_x + 170 - 61 - hand_offset_x, arm_y + hand_offset_y),
    }


def render_config(config: dict) -> np.ndarray:
    """Render a single character configuration to numpy array."""
    canvas = np.zeros((CANVAS_HEIGHT, CANVAS_WIDTH, 4), dtype=np.float32)
    pos = get_positions()
    tint = config["skin_tint"]

    needs_skin_arms = config["sleeve_length"] in ["short", "shorter"]
    needs_skin_legs = config["leg_length"] in ["short", "shorter"]

    # 1. Skin elements
    img = load_image(get_skin_path(tint, "neck"))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["neck"])

    img = load_image(get_skin_path(tint, "head"))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["head"])

    if needs_skin_arms:
        img = load_image(get_skin_path(tint, "arm"))
        if img is not None:
            paste_onto_canvas(canvas, img, pos["right_arm"])
            paste_onto_canvas(canvas, img, pos["left_arm"], flip_horizontal=True)

    if needs_skin_legs:
        img = load_image(get_skin_path(tint, "leg"))
        if img is not None:
            paste_onto_canvas(canvas, img, pos["right_leg"])
            paste_onto_canvas(canvas, img, pos["left_leg"], flip_horizontal=True)

    # 2. Hands, sleeves, pant legs
    img = load_image(get_skin_path(tint, "hand"))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["right_hand"])
        paste_onto_canvas(canvas, img, pos["left_hand"], flip_horizontal=True)

    img = load_image(get_sleeve_path(config["shirt_color"], config["sleeve_length"]))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["right_arm"])
        # Adjust left arm x to align rightmost pixel after flip (sleeve widths vary)
        left_arm_adjusted_x = pos["left_arm"][0] + (170 - img.shape[1])
        paste_onto_canvas(canvas, img, (left_arm_adjusted_x, pos["left_arm"][1]), flip_horizontal=True)

    img = load_image(get_pant_leg_path(config["pants_color"], config["leg_length"]))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["right_leg"])
        paste_onto_canvas(canvas, img, pos["left_leg"], flip_horizontal=True)

    # 3. Pants body
    img = load_image(get_pants_body_path(config["pants_color"], config["pants_style"]))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["pants"])

    # 4. Shirt body
    img = load_image(get_shirt_path(config["shirt_color"], config["shirt_style"]))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["shirt"])

    # 5. Shoes
    img = load_image(get_shoe_path(config["shoe_color"], config["shoe_style"]))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["right_shoe"])
        paste_onto_canvas(canvas, img, pos["left_shoe"], flip_horizontal=True)

    # 6. Facial features
    img = load_image(get_mouth_path(config["mouth_expression"]))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["mouth"])

    img = load_image(get_nose_path(tint, config["nose_style"]))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["nose"])

    img = load_image(get_eye_path(config["eye_color"], config["eye_size"]))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["right_eye"])
        paste_onto_canvas(canvas, img, pos["left_eye"])

    img = load_image(get_eyebrow_path(config["hair_color"], config["eyebrow_style"]))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["right_eyebrow"])
        paste_onto_canvas(canvas, img, pos["left_eyebrow"], flip_horizontal=True)

    # 7. Hair
    img = load_image(get_hair_path(config["hair_color"], config["hair_gender"],
                                   config["hair_style"]))
    if img is not None:
        paste_onto_canvas(canvas, img, pos["hair"])

    return canvas


def render_to_pil(canvas: np.ndarray) -> Image.Image:
    """Convert numpy canvas to PIL Image."""
    canvas_clipped = np.clip(canvas, 0, 255).astype(np.uint8)
    return Image.fromarray(canvas_clipped, mode="RGBA")


# =============================================================================
# Superposition Engine
# =============================================================================

def render_superposition(state: CharacterState, max_samples: int = 100) -> Image.Image:
    """
    Render a superposition of all possible characters given current constraints.
    Averages pixel values across sampled configurations.
    """
    # If too many combinations, sample randomly
    # Estimate number of combinations
    num_configs = 1
    assets = get_assets()

    for prop, _, options_key in CharacterState.PROPERTIES:
        if not state.is_fixed(prop):
            if prop == "hair_style":
                if state.is_fixed("hair_gender"):
                    gender = state.fixed["hair_gender"]
                    if gender == "Man":
                        num_configs *= len(assets["hair_styles_man"])
                    else:
                        num_configs *= len(assets["hair_styles_woman"])
                else:
                    # Average of both
                    num_configs *= max(len(assets["hair_styles_man"]),
                                      len(assets["hair_styles_woman"]))
            elif options_key:
                num_configs *= len(assets[options_key])

    # Generate configs
    if num_configs <= max_samples:
        configs = state.generate_all_configs()
    else:
        # Sample randomly
        configs = [state.sample_config() for _ in range(max_samples)]

    if not configs:
        configs = [state.sample_config()]

    # Render and average
    accumulator = None
    count = 0

    for config in configs:
        canvas = render_config(config)
        if accumulator is None:
            accumulator = canvas.copy()
        else:
            accumulator += canvas
        count += 1

    if count > 0:
        accumulator /= count

    return render_to_pil(accumulator)


def render_samples(state: CharacterState, num_samples: int = 4) -> list:
    """Render multiple random sample characters."""
    samples = []
    for _ in range(num_samples):
        config = state.sample_config()
        canvas = render_config(config)
        samples.append(render_to_pil(canvas))
    return samples


# =============================================================================
# Text UI
# =============================================================================

def print_menu(state: CharacterState):
    """Print the property selection menu."""
    print("\n" + "=" * 60)
    print("AVERAGEFACE - Quantum Character Generator")
    print("=" * 60)
    print("\nCurrent constraints:")

    if not state.fixed:
        print("  (none - showing superposition of ALL characters)")
    else:
        for prop, value in state.fixed.items():
            display = next((d for n, d, _ in CharacterState.PROPERTIES if n == prop), prop)
            print(f"  {display}: {value}")

    print("\nSelect a property to modify:")
    print("-" * 40)

    for i, (prop, display, _) in enumerate(CharacterState.PROPERTIES, 1):
        status = ""
        if state.is_fixed(prop):
            status = f" = {state.fixed[prop]}"
        print(f"  {i:2}. {display}{status}")

    print("-" * 40)
    print("   r. Reset all constraints")
    print("   s. Resample (regenerate random samples)")
    print("   q. Quit")
    print()


def select_value(state: CharacterState, prop: str, display: str):
    """Let user select a value for a property."""
    options = state.get_options(prop)

    print(f"\n{display} options:")
    print("  0. [Clear constraint]" if state.is_fixed(prop) else "  0. [Back]")

    for i, opt in enumerate(options, 1):
        marker = " *" if state.is_fixed(prop) and state.fixed[prop] == opt else ""
        print(f"  {i}. {opt}{marker}")

    try:
        choice = input("\nSelect option: ").strip()
        if not choice:
            return

        idx = int(choice)
        if idx == 0:
            if state.is_fixed(prop):
                state.unfix(prop)
                print(f"Cleared {display} constraint")
        elif 1 <= idx <= len(options):
            value = options[idx - 1]
            state.fix(prop, value)
            print(f"Set {display} to {value}")
    except (ValueError, IndexError):
        print("Invalid selection")


# =============================================================================
# Visualization
# =============================================================================

def save_visualization(state: CharacterState, output_path: Path):
    """Save superposition and samples to a combined image file."""
    print("\nRendering superposition...")
    superposition = render_superposition(state)

    print("Rendering samples...")
    samples = render_samples(state, 4)

    # Create combined image
    padding = 10
    total_width = CANVAS_WIDTH * 5 + padding * 6
    total_height = CANVAS_HEIGHT + padding * 2 + 30  # Extra for title area

    combined = Image.new("RGBA", (total_width, total_height), (255, 255, 255, 255))

    # Paste superposition
    x = padding
    combined.paste(superposition, (x, padding + 30), superposition)

    # Paste samples
    for i, sample in enumerate(samples):
        x = padding + (i + 1) * (CANVAS_WIDTH + padding)
        combined.paste(sample, (x, padding + 30), sample)

    combined.save(output_path)
    print(f"Saved visualization to: {output_path}")

    return combined


def show_visualization(state: CharacterState, plt_module=None):
    """Display superposition and random samples using matplotlib."""
    if plt_module is None:
        import matplotlib.pyplot as plt_module

    print("\nRendering superposition...")
    superposition = render_superposition(state)

    print("Rendering samples...")
    samples = render_samples(state, 4)

    # Create figure with subplots
    fig, axes = plt_module.subplots(1, 5, figsize=(15, 6))
    fig.suptitle("AverageFace: Superposition and Random Samples", fontsize=14)

    # Superposition (larger, on the left)
    axes[0].imshow(superposition)
    axes[0].set_title("Superposition\n(averaged)")
    axes[0].axis("off")

    # Random samples
    for i, sample in enumerate(samples):
        axes[i + 1].imshow(sample)
        axes[i + 1].set_title(f"Sample {i + 1}")
        axes[i + 1].axis("off")

    plt_module.tight_layout()
    plt_module.show(block=False)
    plt_module.pause(0.1)

    return fig


# =============================================================================
# CLI Constraint Handling
# =============================================================================

def print_available_properties():
    """Print all available properties and their valid values."""
    state = CharacterState()
    print("Available properties for --fix:\n")
    for prop, display, _ in CharacterState.PROPERTIES:
        options = state.get_options(prop)
        print(f"  {prop}")
        print(f"    Display name: {display}")
        if options:
            # Format options nicely
            if len(options) <= 6:
                print(f"    Values: {', '.join(str(o) for o in options)}")
            else:
                # Multi-line for long lists
                print(f"    Values: {', '.join(str(o) for o in options[:6])},")
                print(f"            {', '.join(str(o) for o in options[6:])}")
        print()


def apply_cli_constraints(state: CharacterState, fixes: list) -> bool:
    """Apply command-line constraints. Returns False if any are invalid."""
    if not fixes:
        return True

    valid_props = {name for name, _, _ in CharacterState.PROPERTIES}

    for fix_str in fixes:
        if "=" not in fix_str:
            print(f"Error: Invalid format '{fix_str}'. Use PROPERTY=VALUE")
            return False

        prop, value = fix_str.split("=", 1)

        if prop not in valid_props:
            print(f"Error: Unknown property '{prop}'")
            print(f"Valid properties: {', '.join(sorted(valid_props))}")
            return False

        # Convert numeric values
        options = state.get_options(prop)
        if options and isinstance(options[0], int):
            try:
                value = int(value)
            except ValueError:
                print(f"Error: '{prop}' requires an integer value")
                return False

        if options and value not in options:
            print(f"Error: Invalid value '{value}' for '{prop}'")
            print(f"Valid options: {options}")
            return False

        state.fix(prop, value)

    return True


# =============================================================================
# Main
# =============================================================================

def main():
    """Main interactive loop."""
    import argparse

    parser = argparse.ArgumentParser(description="AverageFace - Quantum Character Generator")
    parser.add_argument("--save", "-s", type=str, metavar="FILE",
                       help="Save visualization to file instead of displaying")
    parser.add_argument("--no-display", action="store_true",
                       help="Don't show matplotlib window (use with --save)")
    parser.add_argument("--fix", "-f", action="append", metavar="PROP=VALUE",
                       help="Fix a property (repeatable). Example: --fix hair_color=Blonde")
    parser.add_argument("--list-properties", "-l", action="store_true",
                       help="List all available properties and their valid values")
    args = parser.parse_args()

    if args.list_properties:
        print_available_properties()
        return

    state = CharacterState()

    if not apply_cli_constraints(state, args.fix):
        return

    # Non-interactive mode: just save and exit
    if args.save and args.no_display:
        save_visualization(state, Path(args.save))
        return

    # Try to set up matplotlib for interactive use
    try:
        import matplotlib
        # Try TkAgg first, fall back to other backends
        for backend in ['TkAgg', 'Qt5Agg', 'GTK3Agg', 'Agg']:
            try:
                matplotlib.use(backend)
                break
            except Exception:
                continue
        import matplotlib.pyplot as plt
        has_display = backend != 'Agg'
    except ImportError:
        print("matplotlib not available. Use --save to save images to file.")
        has_display = False
        plt = None

    if not has_display and not args.save:
        print("No display available. Use --save to save images to file.")
        # Fall back to saving
        save_visualization(state, Path("averageface_output.png"))
        return

    fig = None

    # Initial visualization
    if has_display:
        fig = show_visualization(state, plt)
    if args.save:
        save_visualization(state, Path(args.save))

    while True:
        print_menu(state)
        choice = input("Enter choice: ").strip().lower()

        if choice == 'q':
            print("Goodbye!")
            if has_display:
                plt.close('all')
            break
        elif choice == 'r':
            state.reset()
            print("All constraints cleared")
            if has_display:
                plt.close('all')
                fig = show_visualization(state, plt)
            if args.save:
                save_visualization(state, Path(args.save))
        elif choice == 's':
            if has_display:
                plt.close('all')
                fig = show_visualization(state, plt)
            if args.save:
                save_visualization(state, Path(args.save))
        elif choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(CharacterState.PROPERTIES):
                prop, display, _ = CharacterState.PROPERTIES[idx - 1]
                select_value(state, prop, display)
                if has_display:
                    plt.close('all')
                    fig = show_visualization(state, plt)
                if args.save:
                    save_visualization(state, Path(args.save))
            else:
                print("Invalid selection")
        else:
            print("Invalid input")


if __name__ == "__main__":
    main()
