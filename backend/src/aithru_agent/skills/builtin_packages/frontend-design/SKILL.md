---
name: Frontend Design
description: Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, artifacts, posters, or applications (examples include websites, landing pages, dashboards, React components, HTML/CSS layouts, or when styling/beautifying any web UI). Generates creative, polished code and UI design that avoids generic AI aesthetics.
---

# Frontend Design

This skill guides creation of distinctive, production-grade frontend interfaces that avoid generic "AI slop" aesthetics. Implement real working code with exceptional attention to aesthetic details and creative choices.

The user provides frontend requirements: a component, page, application, or interface to build. They may include context about the purpose, audience, or technical constraints.

## Output Requirements

HTML outputs in Aithru are previewable artifacts, not deployed websites by default.

**MANDATORY**: Save standalone HTML deliverables as descriptive kebab-case `.html` files under `/artifacts` (for example, `/artifacts/cosmic-field.html`). Use `media_type: text/html` when creating an artifact directly. If a specific preview is needed, use `presentation.present` with `html_preview`.

Only create a conventional deployable website entry file when the user explicitly asks for a website/app project that needs deployment-style file structure.

## Design Thinking

Before writing any code, pause and clearly define the design direction:

1. **Purpose**: What is the primary goal of this interface? (e.g., convert visitors, showcase a product, tell a story, allow data exploration)
2. **Tone**: What feeling should users have? (e.g., premium and exclusive, playful and energetic, calm and trustworthy, cutting-edge and innovative)
3. **Constraints**: What are the technical or content constraints? (e.g., must be a single HTML file, data from a specific source, specific dimensions, existing brand guidelines)
4. **Differentiation**: What makes this design *unlike* a typical AI-generated interface? (e.g., unique color combinations, unconventional layouts, specific artistic influences, thoughtful micro-interactions)

## Frontend Aesthetics

### Typography
Choose fonts that are distinctive and pair well together:
- **Avoid**: Inter, Roboto, system fonts, Arial — these are the default AI choices
- **Prefer**: Unique, characterful fonts from Google Fonts or other CDNs
- **Pair**: A display font for headings + a readable body font
- **Size**: Use a type scale with dramatic size differences (large headings, comfortable body text)
- Do NOT use font weights below 400 for body text — readability matters

### Color & Theme
- **Avoid**: Purple gradients on white backgrounds (overused AI aesthetic), blue-on-white corporate defaults
- **Prefer**: Curated palettes with purpose — earth tones, bold primaries, monochromatic with one accent, dark mode elegance
- **Backgrounds**: Consider subtle patterns, gradients with depth, dark themes, textured backgrounds
- **Accents**: Use sparingly for emphasis. One accent color is often enough.

### Motion
- Subtle animations that enhance UX: hover states, entrance animations, smooth transitions
- Scroll-triggered reveals for storytelling pages
- GPU-accelerated properties only (transform, opacity) for performance
- Be intentional — don't animate just because you can

### Spatial Composition
- Generous whitespace — negative space is a design element
- Asymmetric layouts for visual interest
- Grid-based layouts with intentional breaks
- Clear visual hierarchy through size, spacing, color, and position

### Background & Visual Details
- Gradients with multiple color stops for depth
- Subtle noise, grain, or texture overlays
- Geometric patterns, organic shapes, decorative elements
- Glass morphism, neumorphism, or other contemporary effects when appropriate

## Anti-Generic Guidance

This is a design skill — avoid generic "AI aesthetics" at all costs. Specifically:

- NEVER use Inter or Roboto fonts
- NEVER use purple-to-blue gradients on white backgrounds
- NEVER use emoji as primary visual elements in the design
- NEVER use stock-looking SVG illustrations without customization
- NEVER rely solely on centered layouts with equal padding

## Code Standards

- Valid, semantic HTML5
- CSS with modern features (custom properties, grid, flexbox, animations)
- JavaScript that is clean and unobtrusive
- Everything in a single descriptive `/artifacts/*.html` file unless otherwise specified
- Responsive design as a baseline, not an afterthought
