---
name: PPT Generation
description: Use this skill when the user requests to generate, create, make, or produce a presentation, slide deck, PowerPoint, PPT, or PPTX file. Supports multiple visual styles, structured content planning, and automated slide generation.
---

# PPT Generation Skill

## Overview

This skill generates professional presentation slide decks in PPTX format. It automates slide planning, content layout, and visual styling to produce ready-to-use presentations.

## Workflow

### Step 1: Understand Requirements

Extract:
- **Topic**: The presentation subject
- **Style**: Visual style preference (see styles below)
- **Slide count**: Approximate number of slides needed
- **Audience**: Who will view this presentation

### Step 2: Create Presentation Plan

Plan the slide-by-slide structure as a JSON outline:

```json
{
  "title": "Presentation Title",
  "slides": [
    {"id": 1, "type": "title", "title": "...", "subtitle": "..."},
    {"id": 2, "type": "content", "title": "...", "bullet_points": ["..."]},
    {"id": 3, "type": "content", "title": "...", "bullet_points": ["..."]},
    {"id": 4, "type": "summary", "title": "Thank You", "bullet_points": ["..."]}
  ]
}
```

### Step 3: Generate Slides

Generate each slide sequentially. Maintain visual consistency across all slides by using the same style, colors, and fonts.

### Step 4: Output

Produce the final PPTX file and present it to the user.

## Presentation Styles

Choose from these visual styles based on the topic and audience:

| Style | Best For | Key Characteristics |
|-------|----------|---------------------|
| **Glassmorphism** | Tech products, SaaS | Frosted glass effects, vibrant backgrounds, layered transparency |
| **Dark Premium** | Executive decks, luxury brands | Dark backgrounds, gold/copper accents, minimalist typography |
| **Gradient Modern** | Startup pitches, creative work | Bold gradients, dynamic layouts, modern fonts |
| **Neo-Brutalist** | Bold statements, creative agencies | Raw borders, primary colors, hard shadows, no gradients |
| **Minimal Swiss** | Academic, consulting, corporate | Clean grids, sans-serif fonts, generous whitespace, neutral palette |
| **Editorial** | Storytelling, thought leadership | Magazine-style layouts, serif headings, large images |
| **3D Isometric** | Product demos, architecture | Isometric illustrations, depth effects, tech-forward look |
| **Keynote** | Apple-style presentations | Clean backgrounds, large typography, high-impact visuals |

## Design Guidelines

### Universal Rules
- Maintain consistent fonts (max 2 per deck)
- Use a cohesive color palette (3-5 colors per deck)
- Ensure sufficient contrast for readability
- Keep bullet points concise (1-2 lines each)
- One key message per slide
- Full-bleed images for visual impact slides

### Color Selection
For each style, define exact hex colors:
- Primary background
- Secondary background
- Primary text
- Secondary text
- Accent color (for highlights, CTAs)

### Typography
- Headings: Large, bold, attention-grabbing
- Body: Readable, clean, comfortable line height
- Size hierarchy: Title (36-48pt), Heading (24-32pt), Body (16-20pt)

## Complete Example

**Topic**: Product Launch — Nova AI Platform
**Style**: Glassmorphism

Slide plan:
1. Title: "Nova AI — The Future of Intelligence" + subtitle
2. Agenda: 3 key points
3. Problem: Current AI limitations (3 bullets)
4. Solution: Nova AI architecture overview
5. Features: 4 key features
6. Demo: Before/After comparison
7. Market: Market size and opportunity
8. Team: Core team highlights
9. Roadmap: Q1-Q4 timeline
10. Thank You: Call to action

## Quality Guidelines

- Be specific with prompts — include exact hex colors, font names, sizes
- Use descriptive language for visual effects (e.g., "frosted glass with 0.8 opacity and 20px blur")
- Embrace negative space for clean, professional look
- Every slide should feel intentional and polished
