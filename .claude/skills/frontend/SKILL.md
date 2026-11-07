---
name: frontend
description: Designs and builds screens that read as a real product rather than generated UI, with one clear primary flow, Geist type, a neutral palette, every state handled and a layout that holds at 390 and 1440 pixels, then reviews them with screenshots. Use for any page, screen, component, layout, style or UI copy, when matching a reference (a screenshot, URL or "make it like X"), and whenever a screen looks bad, looks generated, or looks too simple.
---

# Screens that look like a product

Generated UI fails in two opposite ways. Too much: cards inside cards, an icon on every line, a row
of invented stats, badges, gradients, five colours and six font sizes. Too little: a text box and a
wall of text, so a judge cannot see what the product did. The fix for both is the same: one screen
per job, one focal point, and a result with real structure.

## 1. Decide what each screen is for

Before any code, write three lines per screen in `.work/plan.md`: the user's goal, the one primary
action, and what the result shows. Most hackathon products need one to three screens: the input,
the result, and perhaps history or a detail view.

Leave out what serves no goal: a landing page (unless judged), settings, profiles, a sidebar of
links to pages that do not exist, a dashboard of metrics nobody asked for.

Give the result its structure. The decision or key number comes first, then the evidence for it
(quoted, highlighted or linked), then the detail. Use a table when the data is tabular, and a list
when there are several items of the same kind.

## 2. Start from a reference, never a blank page

- **The user gave one** (screenshot, URL, Figma, "like X"): it is the spec. Take its structure,
  spacing, type scale, colours and copy, and add nothing it lacks. Compare at the same viewport,
  screenshot against screenshot, until the only differences are your data.
- **None was given**: take the layout of a proven pattern. Either a shadcn block (browse
  ui.shadcn.com/blocks, then `npx shadcn@latest add dashboard-01`, `sidebar-07`, `login-03` and so
  on), or the layout of a known clean product in the same category (Linear, Vercel, Stripe,
  Notion, Raycast). Name the reference in the plan, and restyle it to the system below.

## 3. The visual system

Use this unless the spec or the product's brand says otherwise.

- **Type:** Geist Sans for the interface, Geist Mono for numbers, code and IDs.
  - Next.js: create-next-app's layout already loads Geist and Geist Mono from `next/font/google` as
    `--font-geist-sans` and `--font-geist-mono`; keep that. Otherwise `npm i geist`, import
    `GeistSans` from `geist/font/sans` and `GeistMono` from `geist/font/mono`, and put
    `${GeistSans.variable} ${GeistMono.variable}` on `<html>`.
  - Other stacks: `npm i @fontsource-variable/geist @fontsource-variable/geist-mono` and import both
    in the entry file.
  - Either way, [tokens.css](tokens.css) maps them to Tailwind's `font-sans` and `font-mono`.
- **Sizes:** 14 px body, 12 for captions, 16 and 20 for headings, 24 to 30 for the one page title.
  Weights 400, 500 and 600 only. `tabular-nums` on figures.
- **Colour:** copy [tokens.css](tokens.css) over the theme shadcn generates; it explains where each
  block goes. Neutral greys, a near-black primary, and status colours only for status. There is no
  accent until the product has a brand colour; then set `--brand` and use it only for the primary
  action, focus and selection. No violet, purple, indigo, fuchsia or navy, no gradients, glows,
  glass or blurred blobs. Light theme only, unless dark is asked for.
- **Space:** Tailwind's 4 px scale. Page padding 24 (16 on phones), gaps 8, 12, 16 or 24, 32 to 48
  between sections. Content at most `max-w-6xl`; forms and reading text at most `max-w-2xl`.
- **Shape:** one radius (`--radius`, 8 px), 1 px borders in the border colour, shadows only on
  floating things (menus, popovers, dialogs).
- **Icons:** lucide-react at 16 px, only inside dense controls where an icon replaces or clarifies a
  word: search, copy, close, external link, a status. Never beside every heading, card or list item,
  never decorative, never emoji.
- **Components:** shadcn/ui primitives (Button, Input, Textarea, Card, Table, Tabs, Dialog, Sonner,
  Skeleton). Do not hand-roll what shadcn has. A card holds one group of related content, and cards
  never nest.
- **Copy:** short, specific, sentence case. Buttons are verbs ("Analyse posting"). No marketing
  lines, no "AI-powered", no exclamation marks, no lorem ipsum, no invented numbers, testimonials or
  logos, and nothing labelled demo, mock, sample or beta.

## 4. Build every state

Every view that waits on the network has four states. Empty: what to do first, with one example
input to try. Loading: a skeleton shaped like the result, or progress text, with model output
streamed as it arrives. Error: what happened in plain words, and a Retry. Done: the result. Disable
the primary button while it works; never block the whole page.

## 5. Make it hold at every width

Build mobile first and check 390 x 844 and 1440 x 900. One column below 768 px, no horizontal
scroll, tables scroll inside their own container, touch targets at least 40 px, text never under
12 px.

## 6. Review with screenshots, and loop until clean

1. With the app running, run `node .claude/skills/frontend/ui-check.mjs http://localhost:3000`
   (add more URLs for more screens). It needs Playwright once: `npm i -D playwright` and
   `npx playwright install chromium`. It saves screenshots to `.work/screens/` and lists what it can
   measure: horizontal overflow, text under 12 px, saturated colours (violet especially), icons in
   headings, missing Geist, unlabelled controls, console and network errors.
2. Open every screenshot and look at it at full size. Go through the checklist below and write down
   every failure, not only the first.
3. Fix all of them, take new screenshots, and critique them as if seeing them for the first time.
   Repeat until the list is empty.

Reject the screen if any of these is true:

- The primary action is not the most prominent thing, or two things compete for attention.
- More than one accent colour, or any violet, purple, indigo, gradient or glow.
- Decorative shapes, rings or blobs in the background; an uppercase eyebrow line above the title;
  a hero section on a tool, where the title should say what it does and the input should follow.
- Icons or emoji used as decoration on headings, cards or list items.
- Cards inside cards, a box around everything, heavy shadows.
- Edges that do not line up, uneven spacing, more than one corner radius.
- Paragraphs explaining the interface, marketing copy, or any demo, mock, sample or beta label.
- A link, button or menu item that leads nowhere or does nothing.
- An empty, loading or error state that is missing or broken.
- Overflow or a broken layout at 390 px.
- The result of the core job is a wall of text a judge has to read to find the answer.

## When the user says it looks bad

The whole screen failed review, not one detail, so a single tweak is never the answer. Take fresh
screenshots at both sizes, write the complete list of problems area by area (layout, hierarchy,
spacing, type, colour, consistency, states, copy), and fix all of them. If the problems are
structural, rebuild the screen from step 1 instead of patching. Show before and after.
