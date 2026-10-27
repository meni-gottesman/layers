# Updating the Layers website

This guide is for whoever looks after the Layers website from day to day. It
shows you, step by step, how to change the words, photos, hours, specials and
events yourself.

You don't need any technical knowledge, and you can't break the live website.
Every change goes through an automatic check first. If something isn't right,
the website stays exactly as it was, and you get a note that says what to fix.

---

## Cheat sheet

The eight things you'll do most often:

1. **Post an announcement:** This week → **Announcement bar** → switch on **Show the bar** → write the **Message** (and dates if you like) → **Save**.
2. **Add a special:** This week → **Specials** → **Add an entry** → name, photo, description, dates, **Order button** → **Save**.
3. **Add an event:** This week → **Events** → **Add an entry** → **Title**, **Date**, **Starts** → **Save**.
4. **Holiday hours:** This week → **Opening hours** → **Special hours** → **Add an item** → date, name, **Closed all day** or times → **Save**.
5. **Change regular hours:** This week → **Opening hours** → **Weekly hours** → the day → **Opens** / **Closes** → **Save**.
6. **Swap a photo:** shrink it at **/photo-prep** → open the photo spot (for example Pages → **Home** → **Photos** → **Hero photo**) → bin icon → **Upload** → describe it → **Save**.
7. **Add photos to an album:** **Photo albums** → **Edit** the album → **Photos** → **Add an item** → **Upload** → describe it → **Save**.
8. **New prices or menu items:** change them in Square first → **Actions** → **Refresh menu from Square**.

**Made a mistake?** **Actions** → **Undo my last change**.
**Not on the website after 10 minutes?** See [When an update doesn't publish](#when-an-update-doesnt-publish).

---

## Contents

1. [Getting started](#1-getting-started): signing in, a tour of the editor, saving, what each button does
2. [This week](#2-this-week): announcements, specials, events, hours
3. [Photos](#3-photos): the 3 MB limit, swapping photos, focus and zoom, descriptions, albums
4. [Menu](#4-menu)
5. [Pages](#5-pages): words, formatting, how pages show up in Google
6. [Instagram](#6-instagram)
7. [Link in bio, QR codes and the brand kit](#7-link-in-bio-qr-codes-and-the-brand-kit)
8. [Business details](#8-business-details)
9. [The safety net](#9-the-safety-net): checks, problems, undo, backups, when to call for help

---

## Your links

Bookmark these.

| What | Address |
|---|---|
| The website editor | https://app.pagescms.org |
| The website | https://layerssuperfoodbar.com |
| Prepare a photo (shrinks photos so they can be uploaded) | https://layerssuperfoodbar.com/photo-prep |
| Brand kit and QR codes | https://layerssuperfoodbar.com/brand |
| Link in bio page | https://layerssuperfoodbar.com/links |
| Update problems | https://github.com/meni-gottesman/layers/issues |
| List of backups | https://github.com/meni-gottesman/layers/releases |

Until the website moves to layerssuperfoodbar.com, it lives at
https://meni-gottesman.github.io/layers/. In the meantime, use that address
in place of `layerssuperfoodbar.com` in the links above (for example
https://meni-gottesman.github.io/layers/photo-prep). Your website developer
will tell you when the move happens.

---

## How it works, in 30 seconds

- You change things in the **website editor** (it's called Pages CMS) and press **Save**.
- The automatic check reads your change. If all is well, **the website updates by itself about 2–4 minutes later**.
- If something needs fixing, the website stays as it was. A note on the [update problems page](#when-an-update-doesnt-publish) tells you what to fix. Fix it, save again, and the update goes through.
- **Every morning at about 6 am** the website refreshes itself. That's how announcements, specials, events and holiday hours appear and disappear on the right days, even when nobody saves anything.

---

## 1. Getting started

### Signing in for the first time

Your website developer invites you by email. You don't need a GitHub account.

1. Look for an email from **Pages CMS** with a subject like *Join "meni-gottesman/layers" on Pages CMS*. Check your spam folder if it isn't there.
2. Click the **Join** button in the email. **The invitation only works for 24 hours.**
3. A screen called **Verify your login** opens, and a second email arrives: *Your Pages CMS temporary code is …*
4. Type the 6-digit code and press **Verify code**. **Codes last 5 minutes.** If yours has run out, press **Resend code**.
5. The editor opens. You're in.

If you see **Invite unavailable**, the 24 hours have passed. Ask your website
developer to send a new invitation.

### Signing in after that

1. Go to **https://app.pagescms.org**.
2. Type your email address in the **Email** box and press **Continue with email**. Don't use *Sign in with GitHub*.
3. Type the 6-digit code from your email and press **Verify code**.
4. You'll see a **Projects** page. Click **layers** (under *Recently visited* or *Open a project*).

### A tour of the editor

The editor opens on the **Announcement bar**. On the left is the sidebar, in
three parts.

**Content**: everything on the website you can change.

| In the sidebar | What it holds |
|---|---|
| **This week** › **Announcement bar** | The thin bar across the top of every page |
| **This week** › **Specials** | Limited-time drinks and bowls |
| **This week** › **Events** | Run clubs, collabs, pop-ups ("Coming up") |
| **This week** › **Opening hours** | Weekly hours, holiday hours |
| **Menu** | How each Square item is shown on the menu page |
| **Pages** › Home, The Layers Story, How We Make It, What We Make, A Day at Layers, Catering, Visit, FAQ, Link in bio, Gift Cards, Loyalty, Page not found | The words and photos on each page |
| **Photo albums** | The albums on *A Day at Layers* |
| **Instagram** | The Instagram section on the homepage |
| **Business details** | Address, phone, the Square store link, social links |

**This week** and **Pages** are folders: click the name to open or close them.

**Media** › **Photos**: every photo the website uses. You can look, but read
[A few things to avoid](#a-few-things-to-avoid) before changing anything here.

**Actions**: five buttons. See [What each button does](#what-each-button-does).

At the top left it says **layers**, with **main** underneath. It should always
say **main**.

On each editing screen:

- Each box has a label, and many have a short help line underneath. The help lines tell you limits, like "Keep it under 110 characters".
- **Save** is at the top right.
- The **clock icon** next to it shows the last few saves of that screen, and when they were made.
- Long lists (menu items, album photos, questions) have a **dotted grip** on each item. Drag it to change the order. The **bin icon** removes an item.

On a phone the sidebar is tucked away: tap the menu icon at the top left.
Everything works on a phone, but a computer is easier for bigger changes.

### Saving, and what happens next

1. Make your changes, then press **Save** at the top right.
2. A message in the corner says the file was **saved successfully**.
3. Wait about **2–4 minutes**, then reload the page on the website. Your change is there.

Good to know:

- **Leaving a screen without pressing Save throws your changes away.** That's also the way to cancel changes you haven't saved yet.
- **If the editor won't save**, a red message appears under a box (for example *This field is required*) and the corner says *Please fix the errors before saving*. Nothing has been saved yet. Fix that box and press **Save** again.
- **Several saves in a row?** That's fine. The website does one update with all of them.
- **Not there after 10 minutes?** Reload once more (on a phone, close the tab and open it again). Still not there? See [When an update doesn't publish](#when-an-update-doesnt-publish).
- Each save counts as one change for **Undo my last change**. Uploading a photo counts as a change of its own.

### What each button does

| Button | Where | What it does |
|---|---|---|
| **Save** | Top right of every editing screen | Saves this screen. The website updates about 2–4 minutes later. |
| **Add an entry** | The Specials, Events and Photo albums lists | Starts a new special, event or album. |
| **Edit** | Next to each special, event or album in a list | Opens it. |
| **Add an item** | Under a list (special hours, album photos, buttons, questions…) | Adds one more to the list. |
| **Bin icon** | On a list item, or next to a photo | On a list item: removes it (after you confirm). Next to a photo: takes the photo out of that spot so you can choose another. It doesn't delete the photo itself. |
| **Upload** / **Select** | Every photo box (when it's empty) | **Upload** adds a photo from your computer or phone. **Select** picks one that's already on the website. |
| **⋯** or **⋮** menu | Top right of a special, event or album; or beside it in the list | **Delete** removes it completely. Usually it's better to switch off **Published** instead. |
| **Publish now** | Actions | Updates the website again from everything that's saved. Saving already does this, so use it only if the site looks out of date. |
| **Refresh menu from Square** | Actions | Copies the latest items and prices from Square, then republishes. It also runs by itself every morning. |
| **Back up now** | Actions | Makes a copy of all the website's words and photos. A backup is also made by itself every Sunday. |
| **Restore a backup** | Actions | Puts all the words and photos back the way they were in a backup. |
| **Undo my last change** | Actions | Takes back the most recent save, and only that one. |

When you press one of the five **Actions**, a box asks you to confirm. A
message in the corner then follows it, from *"Publish now" is running* to
*"Publish now" succeeded* (or *failed*). The **⋮** next to an action shows its
recent runs: a green tick worked, a red cross didn't. If one fails, the website
stays as it was. Try once more. If it fails again, contact your website
developer, who can see why.

---

## 2. This week

Dates use the date picker: click the box and choose a day. Times use the
24-hour clock, written like **09:00**. For the afternoon, add 12: 1 pm is
**13:00**, 6:30 pm is **18:30**.

### Post an announcement

The announcement bar is the thin strip above the header on every page.

1. Go to **This week** → **Announcement bar**.
2. Switch on **Show the bar**.
3. Write the **Message**. Keep it short: 110 characters at most. The editor won't save a longer one.
4. Optional: to add a link at the end, fill in **both** **Link label** (the words people tap, like *See the menu*) and **Link** (a page on this site like `/menu`, or a full address starting with `https://`).
5. Optional: set **Starts** (the first day it shows) and **Ends** (the last day it shows). Leave them empty to show it straight away and keep it up until you switch it off.
6. Choose the **Colour**: **Green** or **Light (cream, with a green line)**.
7. Press **Save**.

What happens next: the bar appears on every page about 2–4 minutes later. With
a start date in the future, it appears at about 6 am on that day. Visitors can
close the bar with **×**. It then stays closed for them, until you change the
message.

**To take it down:** switch off **Show the bar** and press **Save**. If you set
an end date, it also disappears by itself the day after.

### Add a limited-time special

A special shows in a "Limited time" band on the homepage (after the bowls and
smoothies), at the top of the Menu page, and on the [Link in bio](#7-link-in-bio-qr-codes-and-the-brand-kit)
page. With one special it sits beside its photo; with several they line up in
a row.

1. Go to **This week** → **Specials** → **Add an entry**.
2. **Name**: the drink or bowl, for example *Phi Velvet*. Give each special its own name.
3. Fill in what you like of the rest. Everything else is optional:
   - **Made with (partner)**: shows as "Made with …".
   - **Badge**: the small label above the name, like *Limited time*.
   - **Tagline**: one short line under the name.
   - **Description**: a few sentences. [Formatting](#bold-italic-and-links) works here.
   - **Highlights**: press **Add an item** for each one. Three fit best.
   - **Ingredients**: a list with commas.
   - **Price**: write it like `9.50`.
4. **Photo**: upload a tall (portrait) photo, at least 800 pixels wide. Then fill in **Photo description (alt text)**. See [Writing a photo description](#writing-a-photo-description).
5. **Starts** and **Ends**: optional. Empty means it shows from now until you switch it off.
6. **Order button**: choose one:
   - **No button (in store only)**: no button; the **Availability note** shows instead (it says *In store for a limited time.* unless you change it). Use this when the special isn't on Square.
   - **Order on Square**: a button to Layers' Square store.
   - **Order (to the order link below)**: a button to the address you paste in **Order link**. The link is required for this choice.
7. **Show on the homepage**, **Show on the menu**: on by default. Switch one off to keep the special off that page.
8. Leave **Published** on, and press **Save**.

What happens next: the special shows about 2–4 minutes later, or at about 6 am
on its start date.

Tip: to prepare a special ahead of time, switch **Published** off, save it,
and switch it on when you're ready.

### Take a special down

Any one of these works:

- **Let it end:** set an **Ends** date. It disappears by itself the day after.
- **Switch it off:** open the special (**Edit**), switch off **Published**, and press **Save**. It stays in the list, ready for next time.
- **Delete it:** in the **Specials** list, the **⋮** menu beside it → **Delete**. It's gone for good, unless you use [Undo my last change](#undo-my-last-change) straight away.

Switching it off is usually best.

### Add an event

Events show under **Coming up** in the homepage's community section and on the
Link in bio page, soonest first. They disappear by themselves once the day has
passed.

1. Go to **This week** → **Events** → **Add an entry**.
2. **Title**: for example *Saturday run club*.
3. **Date**: pick the day.
4. **Starts** and **Ends**: optional, like `09:00` and `10:30`. If you give an end time, give a start time too.
5. Optional: **With (partner)** (shows as "With …"), **Location**, **Description**.
6. Optional: a **Photo** (shown as a small square, at least 800 pixels wide) and its **Photo description (alt text)**.
7. Optional: a sign-up or info link. Fill in **both** **Link** and **Link label** (like *Sign up*).
8. Leave **Published** on, and press **Save**.

To take an event down early, switch off **Published** and save.

### Holiday or special hours

Use this for a holiday, a private event, or any one-off day with different
hours. On that date these hours win over the weekly ones.

1. Go to **This week** → **Opening hours**.
2. Under **Special hours**, press **Add an item**.
3. **Date**: pick the day.
4. **Name**: for example *Thanksgiving*.
5. Either switch on **Closed all day**, or fill in **Opens** and **Closes** (like `10:00` and `14:00`).
6. Press **Save**.

What happens next: from 60 days before the date, the day is listed under
**Special hours** on the Visit page and passed on to search engines. On the
day itself, the "Open now" label follows these hours. The weekly hours in the
footer and elsewhere stay as they are. Once the date has passed it stops
showing. You can remove old ones with the bin icon whenever you like.

### Change your regular hours

1. Go to **This week** → **Opening hours** → **Weekly hours**.
2. Open the day. Change **Opens** and **Closes**, or switch on **Closed all day**.
3. Optional: **Note** (at the bottom of the screen) adds a short line under the hours table on the Visit page.
4. Press **Save**.

The new hours appear everywhere at once: the footer of every page, the Visit
page, the homepage, the FAQ, the "Open now" label and the information search
engines read.

This doesn't change your hours on **Google Maps, Yelp or Square**. Update
those separately.

---

## 3. Photos

### Before you upload: the 3 MB limit and "Prepare a photo"

The editor can't upload photos bigger than about **3 MB**, and most phone
photos are bigger. It also only takes **JPEG, PNG or WebP** photos, not the
HEIC photos iPhones often take.

The website has a page that fixes both:
**[layerssuperfoodbar.com/photo-prep](https://layerssuperfoodbar.com/photo-prep)**.

1. Open the Prepare a photo page.
2. Press **Choose a photo** (or drag one onto the page).
3. It shows the size before and after. Press **Download the photo**. The copy is named like `IMG_1234-web.jpg`. On an iPhone or iPad, downloads go to the **Files** app, in **Downloads**.
4. Upload that copy in the editor.

Your photo never leaves your device: the page does the work in your browser.
It also removes hidden details stored in the photo, such as where it was
taken. That matters, because uploaded photos are stored where anyone could
find them.

If the page says it **can't open the photo**, it's probably an iPhone (HEIC)
photo in Chrome. Open the page in **Safari** instead. Or, on a Mac, open the
photo in Preview → File → Export… → Format: JPEG. To make your iPhone take JPEG
photos from now on: Settings → Camera → Formats → **Most Compatible**.

**Photos need to be big enough.** A photo must be at least **800 pixels**
across after it's trimmed to fit its spot. The wide photos that run across the
page need **1,200 pixels**. The prepared copies are plenty big if the original
is. The automatic check tells you if a photo is too small, and the website
stays as it was until you choose a bigger one.

### Swap a photo on a page

Every photo spot on a page has the same four boxes: **Photo**, **Description
(alt text)**, **Focus** and **Zoom**.

1. Prepare the photo (see above).
2. Open the page and find the spot. For example: **Pages** → **Home** → **Photos** → **Hero photo**. The help line under each spot says where it is on the page and what shape it is (wide, tall or square).
3. Next to the current photo, click the **bin icon**. This only takes the photo out of the spot. It doesn't delete it.
4. Press **Upload** and choose your prepared photo. (Or press **Select** to pick a photo that's already on the website.)
5. Rewrite the **Description (alt text)** for the new photo.
6. Leave **Focus** and **Zoom** on **Automatic** to start with. Change them later if the crop isn't right (see below).
7. Press **Save**. Check the page on the website a few minutes later, on a computer and on a phone.

New photos get a light automatic touch-up (colour and brightness), so they sit
well with the others.

On the homepage, **Hero photo** shows on computers and **Hero photo on
phones** on phones. If you change one, you'll probably want to change the
other. They share the hero's description.

### Focus and Zoom, in plain words

Each spot on the website has a fixed shape: wide, tall or square. Your photo
is rarely exactly that shape, so the website trims the edges to fit.

**Focus** says which part of the photo to keep:

- **Automatic** keeps the middle.
- **Top** keeps the top part. Good when heads or faces would be cut off.
- **Bottom** keeps the bottom part. Good for a bowl on a counter low in the photo.
- **Left** and **Right** keep that side.
- **Top left**, **Top right**, **Bottom left**, **Bottom right** keep that corner.

**Zoom** crops in closer:

- **Automatic** and **None**: no zoom. The whole width or height that fits is kept.
- **A little closer**: about 15% closer.
- **Closer**: about 35% closer.

Zooming trims more off the edges, so the photo needs to be bigger. The check
tells you if it's too small.

The photos that were on the site from the start have been fine-tuned by hand.
While such a photo is still in its spot, **Automatic** uses that fine-tuning.
If you change its Focus or Zoom, the fine-tuning is replaced. Set both back to
**Automatic** to get it back.

Rule of thumb: a **landscape** photo for wide spots, a **portrait** photo for
tall ones. A tall photo in a wide spot only keeps a thin band across the
middle. The check warns you when only a small part of a photo will show.

### Writing a photo description

The **Description (alt text)** is read aloud to people who can't see the
photo, for example blind visitors using a screen reader. Search engines read it
too.

Write what someone would need to know if they couldn't see it: who or what is
in the photo, and what's happening.

- One short sentence is usually enough (250 characters at most).
- Don't start with "Photo of" or "Image of". The screen reader already says it's a photo.
- If there are words in the photo, like a sign or a poster, include them.
- Be specific. Instead of *Smoothie*, write *The Phi Velvet: a strawberry-raspberry smoothie swirled with Greek yogurt and topped with cacao nibs, in a Layers cup*.
- Another good one: *Two friends toasting with Layers smoothies outside the shop*.

Most photos must have a description. The check stops the update if one is
missing.

### Add photos to an album

The albums are on the **A Day at Layers** page.

1. Prepare the photos (see [above](#before-you-upload-the-3-mb-limit-and-prepare-a-photo)).
2. Go to **Photo albums** and press **Edit** on the album.
3. Under **Photos**, press **Add an item**.
4. Press **Upload** and choose the photo. Write its **Description (alt text)**.
5. Repeat for each photo. To change the order, drag a photo by its dotted grip.
6. Press **Save**.

To take a photo out of an album, press the bin icon on that item, confirm
**Remove**, and save.

### Create a new album

1. Go to **Photo albums** → **Add an entry**.
2. **Title**: for example *Summer pop-ups*. Each album needs its own title.
3. **Position**: albums are shown smallest number first. The current five are numbered 1 to 5. A new album starts at 99, which puts it last; use 0 to put it first.
4. Add photos as in [Add photos to an album](#add-photos-to-an-album).
5. Optional: a **Cover photo** (see below).
6. Leave **Published** on, and press **Save**.

To put an album together before anyone sees it, switch **Published** off until it's
ready. An album with no photos isn't shown.

### Choose an album's cover photo

The cover is the photo on the album's tile, cut tall (portrait).

1. Open the album (**Photo albums** → **Edit**).
2. **Cover photo**: click the bin icon on the current one, then **Upload** a photo, or **Select** one that's already on the website. Leave it empty to use the album's first photo.
3. **Cover focus**: which part of the photo to keep (see [Focus and Zoom](#focus-and-zoom-in-plain-words)).
4. Press **Save**.

---

## 4. Menu

### Prices, items and descriptions come from Square

The menu page is built from Layers' **Square** online store: item names,
prices, descriptions, ingredients, nutrition and allergens. **To change any of
those, change them in Square first.** The website copies them every morning at
about 5:40 am.

To copy them right away:

1. Make the change in Square.
2. In the editor, go to **Actions** → **Refresh menu from Square** → confirm **Refresh menu**.
3. Wait for *succeeded* (a few minutes). The menu page is then up to date: reload it to check.

New Square items are added to the end of the website's menu list, with
Square's name and photo. Items Square no longer sells drop off the website by
themselves.

Sold-out labels: once your website developer has connected Square's live
updates, items you mark sold out in Square show as sold out on the website
within a few minutes. Until then, the menu shows the morning's copy.

### Change how an item looks on the website

The editor controls how each item is *shown*. None of this changes Square.

1. Go to **Menu**. Scroll to **Items**. Each one is labelled with its category and its name on Square. Click one to open it (or press **Expand all**).
2. Change what you need:
   - **Name on the website**: a different name for the website only. Leave it empty to use Square's name. About 40 characters at most, or it wraps on the cards.
   - **Note under the name**: a short line, like *Classic Açaí*.
   - **Photo**: your own photo in place of Square's (square, at least 800 pixels wide). Leave it empty to use Square's photo. **Focus** and **Zoom** work as on the [pages](#focus-and-zoom-in-plain-words).
   - **Hide from the website**: switch on to leave the item off the website. It stays on Square.
3. Press **Save**.

**Order:** within each category, the menu follows the order of this list. Drag
an item by its dotted grip to move it. You can't move an item to another
category here: that comes from Square.

**Square ID**, **Name on Square** and **Category on Square** are filled in by
Square and can't be changed.

**Don't remove items from this list** with the bin icon. A removed item comes
back on the next refresh, with Square's name and photo. To take an item off
the website, use **Hide from the website**.

The boxes at the top of **Menu** (**Title**, **Introduction**, **Prices
note**, **Allergen note**, **Order button**) are the words around the menu.

---

## 5. Pages

### Edit the words on a page

1. Go to **Pages** and choose the page.
2. The boxes follow the page from top to bottom. Change what you like.
3. Press **Save**.

Some things aren't edited on the page itself:

- Address and hours come from **Business details** and **Opening hours**.
- The albums on *A Day at Layers* are under **Photo albums**.
- The homepage film is changed by your website developer. On **Home** → **Film** you can edit the two texts read aloud to people who can't see it.
- On **Catering**, the form's questions are fixed. Inquiries go to the inbox your website developer set up.
- **FAQ**: press **Add an item** under **Questions** for a new question. Drag questions to change their order. Writing `{hours}` in an answer puts in the current opening hours.
- **Page not found** is the page people see when a link is broken or out of date.

### Bold, italic and links

Some of the bigger text boxes understand a few simple marks:

- **Description** on specials and events
- **Menu** → **Introduction**
- **The Layers Story** → **Chapters** → **Text**
- **How We Make It** → **Text**
- **Catering** → **Introduction**
- **Visit** → **Getting here** → **Text**
- **FAQ** → **Answer**
- **Link in bio** → **Introduction**
- **Gift Cards** → **Text**

In every other box the marks show exactly as typed, so leave them out there.

| You type | It shows as |
|---|---|
| A blank line between two paragraphs | Two separate paragraphs |
| `**Fresh every morning**` | **Fresh every morning** |
| `*made to order*` | *made to order* |
| `[see the menu](/menu)` | a link to the menu page |
| `[our Instagram](https://www.instagram.com/layerssuperfoodbar/)` | a link to another website (it opens in a new tab) |

Links can go to:

- a page on this site, starting with `/` (like `/menu`, `/visit`, `/catering`);
- another website, starting with `https://`;
- an email address (`mailto:hello@example.com`) or a phone number (`tel:+15105550123`).

Anything else shows as plain text. There's no way to add other styles, so the
pages always keep the Layers look.

### How a page shows up in Google (SEO)

At the bottom of most pages is a group called **SEO**. It decides how the page
appears in Google and in link previews (when someone shares the link in a
message).

- **Page title**: the blue headline in Google's results and the name on the browser tab. About **60 characters**; longer titles get cut off.
- **Description**: the one or two sentences under the headline. About **160 characters**; longer ones get cut off.

Write them for a person deciding whether to click: say what the page is, and
mention Berkeley and what makes Layers different. Google can take days or weeks
to show a change, and sometimes picks its own text.

The check warns you about long titles or descriptions, but they don't stop an
update. For pages without their own description, Google uses **Business
details** → **SEO** → **Default description**.

### Gift Cards and Loyalty

These two pages are drafts and aren't on the website yet. You can fill them in
and save them as often as you like. To put one on the website, switch on
**Published**. Two things to know:

- A page that still has placeholder text in square brackets won't go live. The check tells you which box to finish.
- Visitors can only find the page once it's linked from the site's menus. Ask your website developer to add it.

---

## 6. Instagram

The homepage has an Instagram section before the Visit section: a grid of
posts and a "Follow @layerssuperfoodbar" link. It can show posts you pick by
hand, or your latest posts automatically.

Settings on the **Instagram** screen:

- **Show the Instagram section**: switch off to hide the whole section.
- **Heading**: the words above the grid.
- **Posts to show**: **Hand-picked posts (below)** or **Automatic (latest posts)**.
- **Number of posts**: how many squares the grid shows, from 1 to 12.

### Hand-picked posts (how it works now)

1. Go to **Instagram** → **Hand-picked posts** → **Add an item**.
2. **Photo**: upload the photo you posted (prepared at [/photo-prep](#before-you-upload-the-3-mb-limit-and-prepare-a-photo)). It's shown square, so keep the subject near the middle.
3. **Instagram post link**: in the Instagram app, open the post, tap **⋯** → **Copy link**, and paste it here.
4. **Description (alt text)**: describe the photo.
5. Drag the post to where you want it. The grid shows the first posts in the list, up to **Number of posts**.
6. Press **Save**.

### Switching to automatic posts (Behold)

Automatic mode uses a free service called **Behold**, which passes your latest
posts to the website. Here's what to ask for and do:

1. **Layers' Instagram must be a professional account** (Business or Creator). It's free to switch: in the Instagram app, Settings → Account type and tools → Switch to professional account.
2. **Ask your website developer to set up Behold.** They'll send you a link from Behold. Open it, log in to Layers' Instagram, and allow everything it asks for, including the permissions marked optional.
3. Your developer gives you the **feed link**. It starts with `https://feeds.behold.so/`.
4. In the editor: **Instagram** → **Posts to show** → **Automatic (latest posts)** → paste the link into **Behold feed link** → **Save**.

How automatic mode behaves:

- Behold refreshes your posts once a day. The website collects them every morning (and usually when it updates after you save).
- **Behold's free plan gives the latest 6 posts**, so in automatic mode the grid shows 6 at most, even if **Number of posts** is higher.
- Videos and reels show as their cover picture. The photo description comes from your post's alt text or caption.
- If the feed stops working, or has fewer than 3 posts, the website shows your **hand-picked posts** instead. So keep a few hand-picked posts in the list as a backup.
- If Layers' Instagram password changes or the account goes private, Behold can lose its connection. Ask your website developer for the Behold link again.

---

## 7. Link in bio, QR codes and the brand kit

### The Link in bio page (/links)

**layerssuperfoodbar.com/links** is a simple page made for Instagram's "link
in bio". It has big buttons, any current specials and events, and the address
with today's hours at the bottom. It isn't in the site's menus or in Google.

1. Go to **Pages** → **Link in bio**.
2. **Heading** and **Introduction**: the words at the top.
3. **Buttons**: each has a **Label**, a **Link** (a page on this site like `/menu`, or a full `https://` address) and **Highlight** (shows it in Layers green; use it for one button). Press **Add an item** for a new button. Drag to reorder.
4. **Show specials** and **Show events**: switch off to leave them off this page.
5. Press **Save**.

To use it, put `layerssuperfoodbar.com/links` in Layers' Instagram profile:
Edit profile → Links → Add external link.

**Delivery buttons** appear by themselves when there's a DoorDash or Uber Eats
link in **Business details** → **Ordering** (see [Business details](#8-business-details)).

### QR codes and the brand kit (/brand)

**[layerssuperfoodbar.com/brand](https://layerssuperfoodbar.com/brand)** has
everything for posts, flyers and table signs:

- **Logo**: the green wordmark (for light backgrounds), the cream wordmark (for photos and the Layers green), and the face mark (for small square spots like a profile picture). Press **Download**.
- **Colours**: Layers' colours with their codes, and a **Copy** button for each.
- **Typeface**: Archivo, free from Google Fonts, and how the site uses it.
- **QR codes**: **Menu** (opens the menu page), **Order** (opens the Square store) and **Link in bio** (opens the /links page). Each comes as **SVG** (stays sharp at any size; use it for print) and **PNG** (1024 × 1024 pixels; good for posts).
- **Photos**: a short list of photo do's and don'ts.

For QR codes on paper:

- Print them at least **2.5 cm (1 inch)** wide, dark on white, with the white border around them.
- Scan one printed copy with a phone before printing a batch.
- The Menu and Link in bio codes open **layerssuperfoodbar.com**. Before you print, check with your website developer that the website is live at that address.
- The Order code follows the **Square store link** in Business details. If that link ever changes, print new codes.

For large prints, like a sign or a banner, ask the owner for the original logo
files. The ones on this page are sized for screens and social posts.

---

## 8. Business details

**Business details** holds the facts used all over the site:

- **Business**: name, street address, city, state, ZIP code, **Cross streets** (shown under the address on the Visit page), **Phone** and **Public email** (shown in the footer when filled in). The public email must be a public address, never the catering inbox.
- **Ordering**: **Square store link** (every Order button opens it), **DoorDash link** and **Uber Eats link** (when filled in, they show on the Visit page as "Delivery: DoorDash · Uber Eats" and as buttons on Link in bio).
- **Social**: the Instagram handle (just the name, without @) and links to TikTok, Facebook, Yelp and Google. Each shows in the footer when filled in.
- **SEO**: the **Default description** (see [How a page shows up in Google](#how-a-page-shows-up-in-google-seo)) and **Share image**, the photo shown when someone shares a link to the site. Empty means the homepage photo; a wide photo works best.
- **Footer tagline** and **Sign-off tagline**: the lines at the bottom of every page.
- **Analytics**: leave this to your website developer.

All links must start with `https://`.

---

## 9. The safety net

### What the automatic check catches

There are two layers of checks.

**The editor won't save** when:

- a required box is empty (*This field is required*);
- the announcement is over 110 characters;
- a time isn't written like `09:00`;
- a link doesn't start with `https://` (or `/` for a page on this site);
- an Instagram post link, Behold link, price, phone number or email doesn't look right.

**After you save, the automatic check stops the update** (and the website
stays as it was) when, for example:

- a photo is missing, can't be opened, or is too small for its spot;
- a photo has no description;
- a day closes before it opens, or has no times and isn't marked closed;
- an end date is before its start date, or an event ends before it starts;
- a link has no label, or a label has no link;
- the announcement is switched on but has no message;
- a special's order button is set to the order link, but there's no link;
- the same date is in special hours twice;
- a page you switched on still has placeholder text.

**It warns you but still publishes** when, for example, a page title or
description is long, only a small part of a photo will show, a special or
announcement has already ended, or two menu items have the same name.

Things that aren't on the website yet never stop an update: a special, event
or album with **Published** off, a switched-off announcement, or a draft page.
Their notes are kept in a separate folded list.

**What it can't catch:** typos, a wrong price or date, or the wrong photo.
Always look at your change on the website once it's live, on a phone too.

### When an update doesn't publish

You'll know because your change isn't on the website after about 10 minutes.
(Another way to check: press **Publish now** and watch whether it says
*succeeded* or *failed*.)

1. Open the **update problems page**. In the editor, click **layers / main** at the top left → **View on GitHub** → the **Issues** tab. Or use the [bookmark](#your-links). You don't need a GitHub account to read it.
2. If the list is empty, nothing is wrong. Wait a few more minutes and reload the website.
3. If there's an open item called **Website update didn't publish**, open it. It explains what to fix, using the same names as the editor. For example:

   > **What needs fixing**
   > - **Opening hours** › Saturday → Opens: Saturday's opening time (16:00) is not before its closing time (09:00). Check the times — they use the 24-hour clock, so 6pm is 18:00.

   That says: go to **Opening hours** → **Saturday** → **Opens**.
4. Fix it in the editor and press **Save**.
5. A few minutes later the website updates with all your changes, and the item closes itself ("This is fixed").

Good to know:

- Until it's fixed, nothing new goes live, including the morning refresh. Fix problems soon.
- **Worth a look** items don't stop anything. Some are fine to leave, like a description the owner approved that's a little long.
- If the note says the problem is **in the website's code or setup, not your content** (or that the update **ran out of time**), there's nothing for you to do. Your website developer has been told. Your changes are saved and go live with the next good update.
- If **Publish now**, **Undo my last change** or **Restore a backup** says *Cancelled*, that's normal when you saved something else right after: the newer update publishes both changes.
- Would you like an email each time this happens? Ask your website developer. It needs a free GitHub account.

### Undo my last change

This takes back your most recent save, and only that one.

1. Go to **Actions** → **Undo my last change**.
2. In **Undo the last change?**, press **Undo**.
3. Wait for *succeeded* (a few minutes). The website is then updated: reload it to check.

Good to know:

- **One save at a time.** If you saved the announcement and then a special, the first Undo takes back the special. Press it again to take back the announcement too.
- **Uploading a photo is a change of its own.** If you uploaded a photo and then saved the page, the first Undo puts the old photo back on the page. A second Undo removes the uploaded photo.
- **There's no redo.** If you undo something by mistake, make the change again by hand.
- **It skips the morning menu refresh.** That comes from Square; fix the item in Square instead.
- Once started, it can't be stopped.
- If it says *failed*, Undo couldn't take that change back safely. Usually that's because the change included work by your website developer, so it isn't yours to undo. Contact your website developer.
- To throw away changes you **haven't saved yet**, just leave the screen without pressing **Save**.

### Backups

A backup is a copy of all the website's words and photos (and the menu as it
was that day).

- **Automatic:** every Sunday at about 4:20 am.
- **Back up now:** before a big change, like rewriting several pages or reorganising the albums. Go to **Actions** → **Back up now** → confirm **Back up now**. It takes a few minutes.
- The **newest 12 Sunday backups** are kept (about three months), and separately the **newest 6** you make with **Back up now**. Pressing **Back up now** many times never pushes the Sunday backups out.
- To see the list: **layers / main** at the top left → **View on GitHub** → **Releases** (on the right; on a phone, scroll down). Or use the [bookmark](#your-links). Each name says when it was made: `backup-2026-11-01-0423` is 1 November 2026 at 4:23 am.

Backups are public, like the website itself: anyone could download one. So
**never type anything private into the editor**, such as a personal phone
number or the catering inbox.

### Restore a backup

This puts **all** the words and photos back the way they were in a backup.
For one recent mistake, use [Undo my last change](#undo-my-last-change)
instead. Restore is for bigger rollbacks.

1. Look at the list of backups and find the date you want.
2. Go to **Actions** → **Restore a backup**.
3. In **Backup name**, type one of these:
   - `latest`: the newest backup (this is filled in for you);
   - a backup's full name, like `backup-2026-11-01-0423`;
   - a date, like `2026-11-01`: the newest backup from that day.
4. Press **Restore**.
5. Wait for *succeeded* (a few minutes). The website is then updated: reload it to check.

Good to know:

- **Everything changed since that backup is replaced**: words, photos, specials, events, albums and hours.
- The menu goes back to that day's prices too. Press **Refresh menu from Square** afterwards to bring it up to date.
- The backup is checked before anything changes. If it wouldn't pass today's checks, nothing is changed.
- It can't be stopped once started. But a restore **can be undone** with **Undo my last change**.
- If it says *failed*, the name probably didn't match a backup. Check the list and try again. If it fails again, contact your website developer.

### What you can't break

- **The live website.** A change that fails the check never reaches it.
- **The look of the site**: layout, fonts, colours, the menus at the top of each page, and the film.
- **Prices, ingredients and allergen information.** They come from Square.
- **The catering form**, and where inquiries go.
- **The main screens.** Pages, hours, the menu and business details can't be deleted from the editor.
- **Square, Instagram and Google Maps.** Nothing in the editor changes them.

### A few things to avoid

- **Don't delete or rename anything in Media → Photos.** Those photos are used on the website, and a missing one stops the next update. To stop using a photo, just choose another one in its spot. Unused photos do no harm. (If it happens, use **Undo my last change**.)
- **Keep the top left on main.** Don't pick anything under **Branches** in that menu: changes made there never reach the website. If it doesn't say **main**, choose **main** and make your changes again.
- **Don't remove menu items.** Use **Hide from the website** instead.
- **Prefer switching off Published to deleting** specials, events and albums.
- **Never type private information** into any box. Everything in the editor ends up public.

### When to contact your website developer

- You can't sign in, your invitation ran out, or someone else needs access.
- A button says *failed* twice in a row.
- The update problems note says the problem is in the website's code or setup.
- **Undo my last change** fails.
- Something looks wrong on the website and no box in the editor controls it.
- You'd like something the editor can't do: a new page or section, a page added to the site's menus (like Gift Cards or Loyalty), a design change, a new film, changes to the catering form or its inbox, automatic Instagram posts (Behold), live sold-out labels from Square, or a new website address.

---

*Written for the editor as it was in October 2026. If a screen looks a little
different, the steps are almost always the same.*
