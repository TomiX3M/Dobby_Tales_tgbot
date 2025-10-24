from dotenv import load_dotenv
load_dotenv()

import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    PicklePersistence,
    filters,
    ConversationHandler,
)

# Set your API keys
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
FIREWORKS_API_KEY = os.environ.get("FIREWORKS_API_KEY")

if not TELEGRAM_BOT_TOKEN or not FIREWORKS_API_KEY:
    raise ValueError("Missing required environment variables! Set TELEGRAM_BOT_TOKEN and FIREWORKS_API_KEY")



# Fireworks AI configuration
FIREWORKS_URL = "https://api.fireworks.ai/inference/v1/chat/completions"

GENRES = {
    "fantasy": "🐉 Fantasy",
    "scifi": "🚀 Sci-Fi",
    "mystery": "🔍 Mystery",
    "horror": "👻 Horror",
    "romance": "💕 Romance",
    "adventure": "⚔️ Adventure"
}

STORY_MODES = {
    "guided": {"name": "📖 Tell Me a Story", "desc": "AI leads, you react"},
    "adventure": {"name": "🎮 Adventure Mode", "desc": "You make choices"},
    "cowrite": {"name": "✍️ Co-Write", "desc": "Take turns writing"}
}

# Conversation states for character creation
WAITING_NAME, WAITING_TRAITS, WAITING_BACKGROUND = range(3)

def call_llm(messages, system_prompt, max_tokens=500):
    """Call Fireworks AI API with retry logic"""
    payload = {
        "model": "accounts/fireworks/models/llama-v3p1-8b-instruct",
        "messages": [
            {"role": "system", "content": system_prompt}
        ] + messages,
        "max_tokens": max_tokens,
        "temperature": 0.9,
        "top_p": 0.95,
        "frequency_penalty": 0.5,
        "presence_penalty": 0.5,
    }
    
    headers = {
        "Authorization": f"Bearer {FIREWORKS_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(FIREWORKS_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except requests.exceptions.Timeout:
        raise Exception("Request timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Connection error: {str(e)}")
    except KeyError:
        raise Exception("Unexpected response format from AI.")

def generate_story_templates(genre):
    """Generate dynamic story templates using AI"""
    system_prompt = f"""You are a creative story template generator. Generate 3 unique and exciting {genre} story templates.
    
    Format each template EXACTLY like this:
    TEMPLATE 1: [Catchy Title]
    [2-3 sentence exciting premise]
    
    TEMPLATE 2: [Catchy Title]
    [2-3 sentence exciting premise]
    
    TEMPLATE 3: [Catchy Title]
    [2-3 sentence exciting premise]
    
    Make them diverse and intriguing. Keep titles under 5 words."""
    
    try:
        response = call_llm([], system_prompt, max_tokens=400)
        return parse_templates(response)
    except:
        # Fallback templates if AI fails
        return {
            "template_1": {"title": f"{genre.title()} Adventure", "premise": "A thrilling journey begins..."},
            "template_2": {"title": f"The {genre.title()} Mystery", "premise": "Something strange is happening..."},
            "template_3": {"title": f"{genre.title()} Quest", "premise": "An epic quest awaits..."}
        }

def parse_templates(response):
    """Parse AI-generated templates"""
    templates = {}
    lines = response.strip().split('\n')
    current_template = None
    current_premise = []
    
    for line in lines:
        line = line.strip()
        if line.startswith('TEMPLATE'):
            if current_template and current_premise:
                templates[current_template] = {
                    "title": templates[current_template]["title"],
                    "premise": " ".join(current_premise).strip()
                }
            
            parts = line.split(':', 1)
            if len(parts) == 2:
                template_num = parts[0].replace('TEMPLATE', '').strip()
                current_template = f"template_{template_num}"
                title = parts[1].strip()
                templates[current_template] = {"title": title, "premise": ""}
                current_premise = []
        elif line and current_template:
            current_premise.append(line)
    
    # Add last template
    if current_template and current_premise:
        templates[current_template] = {
            "title": templates[current_template]["title"],
            "premise": " ".join(current_premise).strip()
        }
    
    return templates if len(templates) >= 3 else {
        "template_1": {"title": "The Beginning", "premise": "Your adventure starts here..."},
        "template_2": {"title": "New Horizons", "premise": "A new challenge appears..."},
        "template_3": {"title": "The Journey", "premise": "An epic tale unfolds..."}
    }

def get_story_progress(context):
    """Get current story turn count"""
    history = context.user_data.get('story_history', [])
    user_turns = len([msg for msg in history if msg['role'] == 'user'])
    return user_turns

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message with genre selection"""
    buttons = [
        InlineKeyboardButton(text, callback_data=f"genre_{genre}")
        for genre, text in GENRES.items()
    ]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎭 *Welcome to StoryBot!*\n\n"
        "I'll create interactive stories with you using AI.\n"
        "Choose a genre to begin your adventure:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def genre_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle genre selection - show story mode options"""
    query = update.callback_query
    await query.answer()
    
    genre = query.data.replace("genre_", "")
    context.user_data['genre'] = genre
    
    # Create mode selection buttons with back button
    keyboard = [
        [InlineKeyboardButton(
            f"{mode_data['name']}", 
            callback_data=f"mode_{mode_key}"
        )]
        for mode_key, mode_data in STORY_MODES.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Back to Genres", callback_data="back_to_genres")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ Selected: {GENRES[genre]}\n\n"
        "🎭 *Choose your story mode:*\n\n"
        f"📖 *Tell Me a Story* - AI leads, you react\n"
        f"🎮 *Adventure Mode* - You make choices\n"
        f"✍️ *Co-Write* - Take turns writing",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def back_to_genres(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Go back to genre selection"""
    query = update.callback_query
    await query.answer()
    
    buttons = [
        InlineKeyboardButton(text, callback_data=f"genre_{genre}")
        for genre, text in GENRES.items()
    ]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎭 *Choose a genre:*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mode selection - show template or character creation option"""
    query = update.callback_query
    await query.answer()
    
    mode = query.data.replace("mode_", "")
    context.user_data['mode'] = mode
    
    keyboard = [
        [InlineKeyboardButton("🎲 Use Story Template", callback_data="use_template")],
        [InlineKeyboardButton("👤 Create Character First", callback_data="create_character")],
        [InlineKeyboardButton("▶️ Start Immediately", callback_data="start_now")],
        [InlineKeyboardButton("⬅️ Back to Modes", callback_data=f"genre_{context.user_data['genre']}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    mode_name = STORY_MODES[mode]['name']
    mode_desc = STORY_MODES[mode]['desc']
    
    await query.edit_message_text(
        f"✅ Mode: {mode_name}\n"
        f"_{mode_desc}_\n\n"
        "How would you like to begin?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def show_templates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and show dynamic story templates"""
    query = update.callback_query
    await query.answer()
    
    # Show loading message
    loading_msg = await query.edit_message_text(
        "✨ *Crafting unique story templates...*\n\n"
        "🎨 Generating creative ideas\n"
        "⏳ This may take 10-15 seconds\n"
        "☕ Hang tight!",
        parse_mode="Markdown"
    )
    
    try:
        genre = context.user_data.get('genre', 'adventure')
        templates = generate_story_templates(genre)
        context.user_data['templates'] = templates
        
        # Create template buttons
        keyboard = [
            [InlineKeyboardButton(
                templates[key]['title'], 
                callback_data=f"tmpl_{key}"
            )]
            for key in list(templates.keys())[:3]
        ]
        keyboard.append([InlineKeyboardButton("🔄 Generate New Templates", callback_data="use_template")])
        keyboard.append([InlineKeyboardButton("✍️ Write My Own", callback_data="start_now")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"mode_{context.user_data.get('mode', 'guided')}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Format template display
        template_text = f"🎭 *{GENRES[genre]} Story Templates:*\n\n"
        for i, (key, tmpl) in enumerate(list(templates.items())[:3], 1):
            template_text += f"*{i}. {tmpl['title']}*\n_{tmpl['premise']}_\n\n"
        
        await query.edit_message_text(
            template_text + "Choose a template or write your own:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        # Error handling with retry option
        keyboard = [
            [InlineKeyboardButton("🔄 Try Again", callback_data="use_template")],
            [InlineKeyboardButton("▶️ Skip Templates", callback_data="start_now")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"mode_{context.user_data.get('mode', 'guided')}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "⚠️ *Oops! Template generation failed.*\n\n"
            f"Error: {str(e)}\n\n"
            "You can try again or skip to start your story!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

async def template_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template selection"""
    query = update.callback_query
    await query.answer("Template selected! ✨")
    
    template_key = query.data.replace("tmpl_", "")
    template = context.user_data['templates'][template_key]
    context.user_data['template'] = template
    context.user_data['story_history'] = []
    
    await query.edit_message_text(
        f"📖 *{template['title']}*\n\n"
        f"_{template['premise']}_\n\n"
        "━━━━━━━━━━━━━━━\n"
        "✅ *Ready to begin!*\n\n"
        "Type your first message to start the story, or give me a prompt like:\n"
        "• 'I wake up in a mysterious place'\n"
        "• 'The adventure begins'\n"
        "• 'Describe the opening scene'",
        parse_mode="Markdown"
    )

async def start_character_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Begin character creation flow"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "👤 *Character Creation - Step 1/3*\n\n"
        "Let's create your protagonist!\n\n"
        "What is your character's *name*?\n\n"
        "_(Type your answer or /cancel to skip)_",
        parse_mode="Markdown"
    )
    
    return WAITING_NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive character name"""
    name = update.message.text.strip()
    
    # Input validation
    if len(name) < 2 or len(name) > 30:
        await update.message.reply_text(
            "⚠️ Name must be between 2-30 characters.\n"
            "Please try again:"
        )
        return WAITING_NAME
    
    context.user_data['character_name'] = name
    
    await update.message.reply_text(
        f"✅ Great! *{name}* is a wonderful name.\n\n"
        "👤 *Character Creation - Step 2/3*\n\n"
        "Now, describe their *key traits*:\n"
        "Examples: brave, clever, mysterious, kind, ruthless\n\n"
        "_(Separate multiple traits with commas)_",
        parse_mode="Markdown"
    )
    
    return WAITING_TRAITS

async def receive_traits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive character traits"""
    traits = update.message.text.strip()
    
    # Input validation
    if len(traits) < 3:
        await update.message.reply_text(
            "⚠️ Please describe at least one trait.\n"
            "Try again:"
        )
        return WAITING_TRAITS
    
    context.user_data['character_traits'] = traits
    name = context.user_data['character_name']
    
    await update.message.reply_text(
        f"✅ Excellent! {name} sounds interesting.\n\n"
        "👤 *Character Creation - Step 3/3*\n\n"
        "Finally, what's their *background*?\n\n"
        "Examples:\n"
        "• A retired detective seeking redemption\n"
        "• A young wizard from a small village\n"
        "• An ex-soldier turned mercenary\n\n"
        "_(Be creative but concise!)_",
        parse_mode="Markdown"
    )
    
    return WAITING_BACKGROUND

async def receive_background(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive character background and start story"""
    background = update.message.text.strip()
    
    # Input validation
    if len(background) < 10:
        await update.message.reply_text(
            "⚠️ Background too short. Please add more detail.\n"
            "Try again:"
        )
        return WAITING_BACKGROUND
    
    context.user_data['character_background'] = background
    context.user_data['story_history'] = []
    
    name = context.user_data['character_name']
    traits = context.user_data['character_traits']
    
    await update.message.reply_text(
        f"✅ *Character Created!*\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 *Name:* {name}\n"
        f"⭐ *Traits:* {traits}\n"
        f"📜 *Background:* {background}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        "🎬 *Ready to begin!*\n\n"
        "Type anything to start your adventure with {name}!",
        parse_mode="Markdown"
    )
    
    return ConversationHandler.END

async def start_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Skip setup and start story immediately"""
    query = update.callback_query
    await query.answer("Let's go! 🚀")
    
    context.user_data['story_history'] = []
    
    genre = GENRES.get(context.user_data.get('genre', 'adventure'), 'Adventure')
    mode = STORY_MODES.get(context.user_data.get('mode', 'guided'), {}).get('name', 'Story')
    
    await query.edit_message_text(
        f"🎬 *Story Started!*\n\n"
        f"📚 Genre: {genre}\n"
        f"🎭 Mode: {mode}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        "Type your first message to begin the story!\n\n"
        "Ideas:\n"
        "• Set the scene\n"
        "• Introduce a character\n"
        "• Start with action\n"
        "• Ask the AI to begin",
        parse_mode="Markdown"
    )

async def generate_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate story continuation using LLM"""
    user_message = update.message.text
    
    # Initialize story if first message
    if 'story_history' not in context.user_data:
        context.user_data['story_history'] = []
        context.user_data['genre'] = 'adventure'
        context.user_data['mode'] = 'guided'
    
    # Add user message to history
    context.user_data['story_history'].append({
        'role': 'user',
        'content': user_message
    })
    
    # Get turn count
    turn = get_story_progress(context)
    
    # Show dynamic loading message
    loading_messages = [
        "✍️ Crafting your story...",
        "🎨 Painting the scene...",
        "🌟 Weaving the narrative...",
        "📖 Turning the page...",
        "✨ Conjuring the tale..."
    ]
    loading_msg = loading_messages[turn % len(loading_messages)]
    
    status_message = await update.message.reply_text(
        f"{loading_msg}\n_Turn {turn}_",
        parse_mode="Markdown"
    )
    
    # Show typing indicator
    await update.message.chat.send_action("typing")
    
    try:
        # Build system prompt based on mode and character
        genre = context.user_data.get('genre', 'adventure')
        mode = context.user_data.get('mode', 'guided')
        
        system_prompt = build_system_prompt(context.user_data, genre, mode)
        
        # Call LLM
        story_text = call_llm(context.user_data['story_history'], system_prompt)
        
        # Add assistant response to history
        context.user_data['story_history'].append({
            'role': 'assistant',
            'content': story_text
        })
        
        # Delete loading message
        await status_message.delete()
        
        # Send story with options
        keyboard = [
            [InlineKeyboardButton("💾 Save Story", callback_data="save_story")],
            [InlineKeyboardButton("🔄 New Story", callback_data="new_story")],
            [InlineKeyboardButton("❓ Help", callback_data="show_help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Add turn counter to response
        footer = f"\n\n_Turn {turn} • {len(story_text.split())} words_"
        
        await update.message.reply_text(
            story_text + footer,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        # Delete loading message
        await status_message.delete()
        
        # Remove last user message from history since generation failed
        if context.user_data['story_history'] and context.user_data['story_history'][-1]['role'] == 'user':
            context.user_data['story_history'].pop()
        
        # Error handling with retry
        keyboard = [
            [InlineKeyboardButton("🔄 Retry", callback_data="retry_last")],
            [InlineKeyboardButton("💾 Save Progress", callback_data="save_story")],
            [InlineKeyboardButton("🆕 New Story", callback_data="new_story")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ *Oops! Story generation failed.*\n\n"
            f"_{str(e)}_\n\n"
            "Your progress is saved. You can:\n"
            "• Try again (I'll remember your last message)\n"
            "• Save what you have so far\n"
            "• Start a fresh story",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        # Store last failed message for retry
        context.user_data['last_failed_message'] = user_message

async def retry_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retry the last failed generation"""
    query = update.callback_query
    await query.answer("Retrying... 🔄")
    
    # Get the last message
    last_message = context.user_data.get('last_failed_message')
    
    if not last_message:
        await query.edit_message_text("No message to retry. Please type a new message to continue!")
        return
    
    # Add back to history
    context.user_data['story_history'].append({
        'role': 'user',
        'content': last_message
    })
    
    # Show loading
    await query.edit_message_text("🔄 Retrying story generation...\n_Please wait..._", parse_mode="Markdown")
    
    try:
        genre = context.user_data.get('genre', 'adventure')
        mode = context.user_data.get('mode', 'guided')
        system_prompt = build_system_prompt(context.user_data, genre, mode)
        
        # Call LLM
        story_text = call_llm(context.user_data['story_history'], system_prompt)
        
        # Add to history
        context.user_data['story_history'].append({
            'role': 'assistant',
            'content': story_text
        })
        
        # Clear failed message
        context.user_data.pop('last_failed_message', None)
        
        turn = get_story_progress(context)
        
        keyboard = [
            [InlineKeyboardButton("💾 Save Story", callback_data="save_story")],
            [InlineKeyboardButton("🔄 New Story", callback_data="new_story")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        footer = f"\n\n_Turn {turn} • {len(story_text.split())} words_"
        
        await query.edit_message_text(
            f"✅ *Success!*\n\n{story_text}{footer}",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        # Remove from history again
        if context.user_data['story_history'] and context.user_data['story_history'][-1]['role'] == 'user':
            context.user_data['story_history'].pop()
        
        keyboard = [
            [InlineKeyboardButton("🔄 Try Again", callback_data="retry_last")],
            [InlineKeyboardButton("🆕 Give Up, New Story", callback_data="new_story")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ *Still failed:* {str(e)}\n\n"
            "The AI service might be having issues. Try again or start fresh.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

def build_system_prompt(user_data, genre, mode):
    """Build dynamic system prompt based on user choices"""
    base_prompt = f"You are a creative storyteller specializing in {genre} stories."
    
    # Add mode-specific instructions
    if mode == "guided":
        base_prompt += "\nYou lead the story. Create engaging narratives that respond to the user's reactions. Keep responses to 2-3 paragraphs."
    elif mode == "adventure":
        base_prompt += "\nPresent the user with meaningful choices. End each response with 2-3 options for what they can do next. Format like: 'What do you do? A) ... B) ... C) ...'"
    elif mode == "cowrite":
        base_prompt += "\nYou and the user take turns writing the story. Build on what they write, then pause for their next contribution. Keep responses to 1-2 paragraphs."
    
    # Add character info if exists
    if 'character_name' in user_data:
        name = user_data['character_name']
        traits = user_data.get('character_traits', 'mysterious')
        background = user_data.get('character_background', 'an adventurer')
        base_prompt += f"\n\nThe protagonist is {name}, who is {traits}. Background: {background}. Keep this character consistent throughout the story."
    
    # Add template context if exists
    if 'template' in user_data:
        template = user_data['template']
        base_prompt += f"\n\nStory premise: {template['premise']}"
    
    base_prompt += "\n\nBe descriptive, engaging, and immersive. Keep the user engaged!"
    
    return base_prompt

async def save_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export story as a text file"""
    query = update.callback_query
    await query.answer("Preparing your story... 📚")
    
    if 'story_history' not in context.user_data or len(context.user_data['story_history']) == 0:
        await query.edit_message_text("No story to save yet! Start writing first.")
        return
    
    # Show progress
    await query.edit_message_text("💾 Saving your story...\n_Formatting document..._", parse_mode="Markdown")
    
    # Format story as text
    genre = context.user_data.get('genre', 'adventure')
    mode = STORY_MODES.get(context.user_data.get('mode', 'guided'), {}).get('name', 'Story')
    turn_count = get_story_progress(context)
    
    story_text = f"{'='*50}\n"
    story_text += f"  {GENRES.get(genre, 'Story')} - {mode}\n"
    story_text += f"  Turns: {turn_count}\n"
    story_text += f"{'='*50}\n\n"
    
    # Add character info if exists
    if 'character_name' in context.user_data:
        story_text += f"PROTAGONIST: {context.user_data['character_name']}\n"
        story_text += f"TRAITS: {context.user_data.get('character_traits', 'N/A')}\n"
        story_text += f"BACKGROUND: {context.user_data.get('character_background', 'N/A')}\n\n"
        story_text += f"{'-'*50}\n\n"
    
    for i, msg in enumerate(context.user_data['story_history'], 1):
        if msg['role'] == 'user':
            story_text += f"🧑 YOU (Turn {(i+1)//2}):\n{msg['content']}\n\n"
        else:
            story_text += f"📖 STORY:\n{msg['content']}\n\n"
        story_text += f"{'-'*50}\n\n"
    
    word_count = sum(len(msg['content'].split()) for msg in context.user_data['story_history'])
    story_text += f"\n{'='*50}\n"
    story_text += f"Total words: {word_count}\n"
    story_text += f"Generated by StoryBot\n"
    story_text += f"{'='*50}"
    
    # Send as file
    await query.message.reply_document(
        document=story_text.encode('utf-8'),
        filename=f"story_{genre}_{turn_count}turns.txt",
        caption=f"📚 *Your Story Saved!*\n\n"
                f"• {turn_count} turns\n"
                f"• {word_count} words\n"
                f"• {len(context.user_data['story_history'])} exchanges\n\n"
                f"_Keep creating! Type to continue or /start for a new story._",
        parse_mode="Markdown"
    )
    
    await query.message.reply_text(
        "✅ Story saved successfully!",
    )

async def new_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a fresh story"""
    query = update.callback_query
    await query.answer()
    
    # Check if there's an active story
    has_story = 'story_history' in context.user_data and len(context.user_data.get('story_history', [])) > 0
    
    if has_story:
        # Confirm before clearing
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Start Fresh", callback_data="confirm_new_story")],
            [InlineKeyboardButton("❌ No, Keep Writing", callback_data="cancel_new_story")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        turn_count = get_story_progress(context)
        await query.edit_message_text(
            f"⚠️ *Are you sure?*\n\n"
            f"You have an active story with {turn_count} turns.\n"
            f"Starting a new story will clear your progress.\n\n"
            f"_(You can save your current story first!)_",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        # No active story, go straight to genre selection
        await confirm_new_story(update, context)

async def confirm_new_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm and start new story"""
    query = update.callback_query
    await query.answer("Starting fresh! 🎬")
    
    # Clear story data
    context.user_data.clear()
    
    buttons = [
        InlineKeyboardButton(text, callback_data=f"genre_{genre}")
        for genre, text in GENRES.items()
    ]
    keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎭 *Choose a genre for your new story:*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def cancel_new_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel new story creation"""
    query = update.callback_query
    await query.answer("Cancelled ✓")
    
    turn_count = get_story_progress(context)
    
    await query.edit_message_text(
        f"✅ *Story Preserved!*\n\n"
        f"Your story with {turn_count} turns is safe.\n"
        f"Type anything to continue writing!",
        parse_mode="Markdown"
    )
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information"""
    await update.message.reply_text(
        "🎭 *StoryBot Commands*\n\n"
        "/start - Begin a new story\n"
        "/help - Show this help message\n\n"
        "*Features:*\n"
        "• Multiple story modes\n"
        "• Character creation\n"
        "• AI-generated story templates\n"
        "• Save your stories\n\n"
        "*How it works:*\n"
        "1. Choose a genre\n"
        "2. Pick your story mode\n"
        "3. Optionally create a character or use a template\n"
        "4. Start writing your adventure!\n\n"
        "The AI will guide you through an interactive storytelling experience! 📖",
        parse_mode="Markdown"
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel character creation"""
    await update.message.reply_text(
        "Character creation cancelled. Use /start to begin a new story!"
    )
    return ConversationHandler.END

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help as callback"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("⬅️ Back to Story", callback_data="close_help")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎭 *StoryBot Help*\n\n"
        "*Commands:*\n"
        "/start - Begin a new story\n"
        "/help - Show this help\n"
        "/cancel - Cancel character creation\n\n"
        "*Tips:*\n"
        "• Be specific in your prompts\n"
        "• Use back buttons to change choices\n"
        "• Save progress regularly\n"
        "• Try different modes!\n\n"
        "Type to continue your story! 📖",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def close_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Close help and return"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "💬 Type your next message to continue the story!"
    )

def main():
    """Start the bot"""
    persistence = PicklePersistence(filepath="bot_data.pickle")
    
    application = (
        Application.builder()
        .token(os.environ.get("TELEGRAM_BOT_TOKEN"))
        .persistence(persistence)
        .build()
    )
    
    # Character creation conversation handler
    char_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_character_creation, pattern="^create_character$")],
        states={
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
            WAITING_TRAITS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_traits)],
            WAITING_BACKGROUND: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_background)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(genre_selected, pattern="^genre_"))
    application.add_handler(CallbackQueryHandler(back_to_genres, pattern="^back_to_genres$"))
    application.add_handler(CallbackQueryHandler(mode_selected, pattern="^mode_"))
    application.add_handler(CallbackQueryHandler(show_templates, pattern="^use_template$"))
    application.add_handler(CallbackQueryHandler(template_selected, pattern="^tmpl_"))
    application.add_handler(CallbackQueryHandler(start_now, pattern="^start_now$"))
    application.add_handler(CallbackQueryHandler(retry_last, pattern="^retry_last$"))
    application.add_handler(CallbackQueryHandler(show_help, pattern="^show_help$"))
    application.add_handler(CallbackQueryHandler(close_help, pattern="^close_help$"))
    application.add_handler(CallbackQueryHandler(confirm_new_story, pattern="^confirm_new_story$"))
    application.add_handler(CallbackQueryHandler(cancel_new_story, pattern="^cancel_new_story$"))
    application.add_handler(char_handler)
    application.add_handler(CallbackQueryHandler(save_story, pattern="^save_story$"))
    application.add_handler(CallbackQueryHandler(new_story, pattern="^new_story$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, generate_story))
    print("🤖 Bot is running with enhanced features...")
    print("✨ Story modes, character creation, and AI templates enabled!")
    application.run_polling()

if __name__ == "__main__":
    main()




#  import os
# import requests
# from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
# from telegram.ext import (
#     Application,
#     CommandHandler,
#     MessageHandler,
#     CallbackQueryHandler,
#     ContextTypes,
#     PicklePersistence,
#     filters,
#     ConversationHandler,
# )

# # Set your API keys
# os.environ["TELEGRAM_BOT_TOKEN"] = "8486480960:AAG_ZzbBHM4153N2gh2x5utaxZFR-PUEgTE"
# os.environ["FIREWORKS_API_KEY"] = "fw_3ZbSYLcy2wvTVvVZ5JMZ2qfJ"

# # Fireworks AI configuration
# FIREWORKS_API_KEY = os.environ.get("FIREWORKS_API_KEY")
# FIREWORKS_URL = "https://api.fireworks.ai/inference/v1/chat/completions"

# GENRES = {
#     "fantasy": "🐉 Fantasy",
#     "scifi": "🚀 Sci-Fi",
#     "mystery": "🔍 Mystery",
#     "horror": "👻 Horror",
#     "romance": "💕 Romance",
#     "adventure": "⚔️ Adventure"
# }

# STORY_MODES = {
#     "guided": {"name": "📖 Tell Me a Story", "desc": "AI leads, you react"},
#     "adventure": {"name": "🎮 Adventure Mode", "desc": "You make choices"},
#     "cowrite": {"name": "✍️ Co-Write", "desc": "Take turns writing"}
# }

# # Conversation states for character creation
# WAITING_NAME, WAITING_TRAITS, WAITING_BACKGROUND = range(3)

# def call_llm(messages, system_prompt, max_tokens=500):
#     """Call Fireworks AI API"""
#     payload = {
#         "model": "accounts/sentientfoundation/models/dobby-unhinged-llama-3-3-70b-new",
#         "messages": [
#             {"role": "system", "content": system_prompt}
#         ] + messages,
#         "max_tokens": max_tokens,
#         "temperature": 0.9,
#         "top_p": 0.95,
#         "frequency_penalty": 0.5,
#         "presence_penalty": 0.5,
#     }
    
#     headers = {
#         "Authorization": f"Bearer {FIREWORKS_API_KEY}",
#         "Content-Type": "application/json"
#     }
    
#     response = requests.post(FIREWORKS_URL, json=payload, headers=headers)
#     response.raise_for_status()
    
#     result = response.json()
#     return result['choices'][0]['message']['content']

# def generate_story_templates(genre):
#     """Generate dynamic story templates using AI"""
#     system_prompt = f"""You are a creative story template generator. Generate 3 unique and exciting {genre} story templates.
    
#     Format each template EXACTLY like this:
#     TEMPLATE 1: [Catchy Title]
#     [2-3 sentence exciting premise]
    
#     TEMPLATE 2: [Catchy Title]
#     [2-3 sentence exciting premise]
    
#     TEMPLATE 3: [Catchy Title]
#     [2-3 sentence exciting premise]
    
#     Make them diverse and intriguing. Keep titles under 5 words."""
    
#     try:
#         response = call_llm([], system_prompt, max_tokens=400)
#         return parse_templates(response)
#     except:
#         # Fallback templates if AI fails
#         return {
#             "template_1": {"title": f"{genre.title()} Adventure", "premise": "A thrilling journey begins..."},
#             "template_2": {"title": f"The {genre.title()} Mystery", "premise": "Something strange is happening..."},
#             "template_3": {"title": f"{genre.title()} Quest", "premise": "An epic quest awaits..."}
#         }

# def parse_templates(response):
#     """Parse AI-generated templates"""
#     templates = {}
#     lines = response.strip().split('\n')
#     current_template = None
#     current_premise = []
    
#     for line in lines:
#         line = line.strip()
#         if line.startswith('TEMPLATE'):
#             if current_template and current_premise:
#                 templates[current_template] = {
#                     "title": templates[current_template]["title"],
#                     "premise": " ".join(current_premise).strip()
#                 }
            
#             parts = line.split(':', 1)
#             if len(parts) == 2:
#                 template_num = parts[0].replace('TEMPLATE', '').strip()
#                 current_template = f"template_{template_num}"
#                 title = parts[1].strip()
#                 templates[current_template] = {"title": title, "premise": ""}
#                 current_premise = []
#         elif line and current_template:
#             current_premise.append(line)
    
#     # Add last template
#     if current_template and current_premise:
#         templates[current_template] = {
#             "title": templates[current_template]["title"],
#             "premise": " ".join(current_premise).strip()
#         }
    
#     return templates if len(templates) >= 3 else {
#         "template_1": {"title": "The Beginning", "premise": "Your adventure starts here..."},
#         "template_2": {"title": "New Horizons", "premise": "A new challenge appears..."},
#         "template_3": {"title": "The Journey", "premise": "An epic tale unfolds..."}
#     }

# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Welcome message with genre selection"""
#     buttons = [
#         InlineKeyboardButton(text, callback_data=f"genre_{genre}")
#         for genre, text in GENRES.items()
#     ]
#     keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
#     reply_markup = InlineKeyboardMarkup(keyboard)
    
#     await update.message.reply_text(
#         "🎭 *Welcome to StoryBot!*\n\n"
#         "I'll create interactive stories with you using AI.\n"
#         "Choose a genre to begin your adventure:",
#         reply_markup=reply_markup,
#         parse_mode="Markdown"
#     )

# async def genre_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Handle genre selection - show story mode options"""
#     query = update.callback_query
#     await query.answer()
    
#     genre = query.data.replace("genre_", "")
#     context.user_data['genre'] = genre
    
#     # Create mode selection buttons
#     keyboard = [
#         [InlineKeyboardButton(
#             f"{mode_data['name']}\n{mode_data['desc']}", 
#             callback_data=f"mode_{mode_key}"
#         )]
#         for mode_key, mode_data in STORY_MODES.items()
#     ]
#     reply_markup = InlineKeyboardMarkup(keyboard)
    
#     await query.edit_message_text(
#         f"Great! You chose {GENRES[genre]}\n\n"
#         "🎭 *Choose your story mode:*",
#         reply_markup=reply_markup,
#         parse_mode="Markdown"
#     )

# async def mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Handle mode selection - show template or character creation option"""
#     query = update.callback_query
#     await query.answer()
    
#     mode = query.data.replace("mode_", "")
#     context.user_data['mode'] = mode
    
#     keyboard = [
#         [InlineKeyboardButton("🎲 Use Story Template", callback_data="use_template")],
#         [InlineKeyboardButton("👤 Create Character First", callback_data="create_character")],
#         [InlineKeyboardButton("▶️ Start Immediately", callback_data="start_now")]
#     ]
#     reply_markup = InlineKeyboardMarkup(keyboard)
    
#     mode_name = STORY_MODES[mode]['name']
#     await query.edit_message_text(
#         f"Mode selected: {mode_name}\n\n"
#         "How would you like to begin?",
#         reply_markup=reply_markup
#     )

# async def show_templates(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Generate and show dynamic story templates"""
#     query = update.callback_query
#     await query.answer("Generating story ideas...")
    
#     await query.edit_message_text("✨ Crafting unique story templates for you...\n⏳ This may take a moment...")
    
#     genre = context.user_data.get('genre', 'adventure')
#     templates = generate_story_templates(genre)
#     context.user_data['templates'] = templates
    
#     # Create template buttons
#     keyboard = [
#         [InlineKeyboardButton(
#             templates[key]['title'], 
#             callback_data=f"tmpl_{key}"
#         )]
#         for key in list(templates.keys())[:3]
#     ]
#     keyboard.append([InlineKeyboardButton("🔄 Generate New Templates", callback_data="use_template")])
#     keyboard.append([InlineKeyboardButton("✍️ Write My Own", callback_data="start_now")])
    
#     reply_markup = InlineKeyboardMarkup(keyboard)
    
#     # Format template display
#     template_text = f"🎭 *{GENRES[genre]} Story Templates:*\n\n"
#     for i, (key, tmpl) in enumerate(list(templates.items())[:3], 1):
#         template_text += f"*{i}. {tmpl['title']}*\n{tmpl['premise']}\n\n"
    
#     await query.edit_message_text(
#         template_text + "Choose a template or write your own:",
#         reply_markup=reply_markup,
#         parse_mode="Markdown"
#     )

# async def template_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Handle template selection"""
#     query = update.callback_query
#     await query.answer()
    
#     template_key = query.data.replace("tmpl_", "")
#     template = context.user_data['templates'][template_key]
#     context.user_data['template'] = template
    
#     await query.edit_message_text(
#         f"📖 *{template['title']}*\n\n"
#         f"{template['premise']}\n\n"
#         "Perfect! Now type anything to begin your story!",
#         parse_mode="Markdown"
#     )

# async def start_character_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Begin character creation flow"""
#     query = update.callback_query
#     await query.answer()
    
#     await query.edit_message_text(
#         "👤 *Character Creation*\n\n"
#         "Let's create your protagonist!\n\n"
#         "What is your character's *name*?",
#         parse_mode="Markdown"
#     )
    
#     return WAITING_NAME

# async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Receive character name"""
#     name = update.message.text.strip()
#     context.user_data['character_name'] = name
    
#     await update.message.reply_text(
#         f"Great! {name} is a wonderful name.\n\n"
#         "Now, describe their *key traits* (e.g., brave, clever, mysterious, kind):\n"
#         "Separate multiple traits with commas.",
#         parse_mode="Markdown"
#     )
    
#     return WAITING_TRAITS

# async def receive_traits(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Receive character traits"""
#     traits = update.message.text.strip()
#     context.user_data['character_traits'] = traits
    
#     name = context.user_data['character_name']
    
#     await update.message.reply_text(
#         f"Excellent! {name} sounds interesting.\n\n"
#         "Finally, what's their *background*?\n"
#         "(e.g., 'A retired detective seeking redemption' or 'A young wizard from a small village')",
#         parse_mode="Markdown"
#     )
    
#     return WAITING_BACKGROUND

# async def receive_background(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Receive character background and start story"""
#     background = update.message.text.strip()
#     context.user_data['character_background'] = background
#     context.user_data['story_history'] = []
    
#     name = context.user_data['character_name']
#     traits = context.user_data['character_traits']
    
#     await update.message.reply_text(
#         f"✅ *Character Created!*\n\n"
#         f"*Name:* {name}\n"
#         f"*Traits:* {traits}\n"
#         f"*Background:* {background}\n\n"
#         "Perfect! Now type anything to begin your adventure!",
#         parse_mode="Markdown"
#     )
    
#     return ConversationHandler.END

# async def start_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Skip setup and start story immediately"""
#     query = update.callback_query
#     await query.answer()
    
#     context.user_data['story_history'] = []
    
#     await query.edit_message_text(
#         "🎬 Ready to begin!\n\n"
#         "Type anything to start your story, or give me a prompt!"
#     )

# async def generate_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Generate story continuation using LLM"""
#     user_message = update.message.text
    
#     # Initialize story if first message
#     if 'story_history' not in context.user_data:
#         context.user_data['story_history'] = []
#         context.user_data['genre'] = 'adventure'
#         context.user_data['mode'] = 'guided'
    
#     # Add user message to history
#     context.user_data['story_history'].append({
#         'role': 'user',
#         'content': user_message
#     })
    
#     # Show typing indicator
#     await update.message.chat.send_action("typing")
    
#     try:
#         # Build system prompt based on mode and character
#         genre = context.user_data.get('genre', 'adventure')
#         mode = context.user_data.get('mode', 'guided')
        
#         system_prompt = build_system_prompt(context.user_data, genre, mode)
        
#         # Call LLM
#         story_text = call_llm(context.user_data['story_history'], system_prompt)
        
#         # Add assistant response to history
#         context.user_data['story_history'].append({
#             'role': 'assistant',
#             'content': story_text
#         })
        
#         # Send story with options
#         keyboard = [
#             [InlineKeyboardButton("💾 Save Story", callback_data="save_story")],
#             [InlineKeyboardButton("🔄 New Story", callback_data="new_story")]
#         ]
#         reply_markup = InlineKeyboardMarkup(keyboard)
        
#         await update.message.reply_text(
#             story_text,
#             reply_markup=reply_markup
#         )
        
#     except Exception as e:
#         await update.message.reply_text(
#             f"⚠️ Sorry, something went wrong: {str(e)}\n"
#             "Please try again or start a new story with /start"
#         )

# def build_system_prompt(user_data, genre, mode):
#     """Build dynamic system prompt based on user choices"""
#     base_prompt = f"You are a creative storyteller specializing in {genre} stories."
    
#     # Add mode-specific instructions
#     if mode == "guided":
#         base_prompt += "\nYou lead the story. Create engaging narratives that respond to the user's reactions. Keep responses to 2-3 paragraphs."
#     elif mode == "adventure":
#         base_prompt += "\nPresent the user with meaningful choices. End each response with 2-3 options for what they can do next. Format like: 'What do you do? A) ... B) ... C) ...'"
#     elif mode == "cowrite":
#         base_prompt += "\nYou and the user take turns writing the story. Build on what they write, then pause for their next contribution. Keep responses to 1-2 paragraphs."
    
#     # Add character info if exists
#     if 'character_name' in user_data:
#         name = user_data['character_name']
#         traits = user_data.get('character_traits', 'mysterious')
#         background = user_data.get('character_background', 'an adventurer')
#         base_prompt += f"\n\nThe protagonist is {name}, who is {traits}. Background: {background}. Keep this character consistent throughout the story."
    
#     # Add template context if exists
#     if 'template' in user_data:
#         template = user_data['template']
#         base_prompt += f"\n\nStory premise: {template['premise']}"
    
#     base_prompt += "\n\nBe descriptive, engaging, and immersive. Keep the user engaged!"
    
#     return base_prompt

# async def save_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Export story as a text file"""
#     query = update.callback_query
#     await query.answer()
    
#     if 'story_history' not in context.user_data or len(context.user_data['story_history']) == 0:
#         await query.edit_message_text("No story to save!")
#         return
    
#     # Format story as text
#     genre = context.user_data.get('genre', 'adventure')
#     mode = STORY_MODES.get(context.user_data.get('mode', 'guided'), {}).get('name', 'Story')
    
#     story_text = f"{'='*50}\n"
#     story_text += f"  {GENRES.get(genre, 'Story')} - {mode}\n"
#     story_text += f"{'='*50}\n\n"
    
#     # Add character info if exists
#     if 'character_name' in context.user_data:
#         story_text += f"PROTAGONIST: {context.user_data['character_name']}\n"
#         story_text += f"TRAITS: {context.user_data.get('character_traits', 'N/A')}\n"
#         story_text += f"BACKGROUND: {context.user_data.get('character_background', 'N/A')}\n\n"
#         story_text += f"{'-'*50}\n\n"
    
#     for msg in context.user_data['story_history']:
#         if msg['role'] == 'user':
#             story_text += f"🧑 YOU:\n{msg['content']}\n\n"
#         else:
#             story_text += f"📖 STORY:\n{msg['content']}\n\n"
#         story_text += f"{'-'*50}\n\n"
    
#     # Send as file
#     await query.message.reply_document(
#         document=story_text.encode('utf-8'),
#         filename=f"story_{genre}_{mode}.txt",
#         caption="Here's your story! 📚"
#     )

# async def new_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Start a fresh story"""
#     query = update.callback_query
#     await query.answer()
    
#     # Clear story data but keep it simple
#     context.user_data.clear()
    
#     buttons = [
#         InlineKeyboardButton(text, callback_data=f"genre_{genre}")
#         for genre, text in GENRES.items()
#     ]
#     keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
#     reply_markup = InlineKeyboardMarkup(keyboard)
    
#     await query.edit_message_text(
#         "🎭 Choose a genre for your new story:",
#         reply_markup=reply_markup
#     )