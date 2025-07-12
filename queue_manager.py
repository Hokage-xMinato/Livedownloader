# queue_manager.py
import time

owner_ids = set()
cooldown_db = {}  # user_id: timestamp when cooldown ends


def set_owner(user_id):
    owner_ids.add(user_id)

def is_owner(user_id):
    return user_id in owner_ids

def user_on_cooldown(user_id):
    until = cooldown_db.get(user_id)
    return until and until > time.time()

def block_user_temporarily(user_id, seconds):
    cooldown_db[user_id] = time.time() + seconds


def cancel_task(user_id, queue, running_tasks):
    if user_id in running_tasks:
        del running_tasks[user_id]
        return True

    temp_queue = []
    cancelled = False
    while not queue.empty():
        task = queue.get_nowait()
        if task['user_id'] == user_id:
            cancelled = True
            continue
        temp_queue.append(task)

    for task in temp_queue:
        queue.put_nowait(task)

    return cancelled


async def queue_handler(queue, running_tasks, user_states, event, task_data, client):
    user_id = task_data['user_id']

    if is_owner(user_id):
        queue.put_nowait(task_data)
        await event.respond("🟢 Queued as owner. Starting soon...")
        return

    queue.put_nowait(task_data)
    await event.respond("⏳ Added to queue. Please wait...")
