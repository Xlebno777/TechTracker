<template>
  <span
    ref="triggerRef"
    class="tt-info-hint"
    tabindex="0"
    @mouseenter="openHint"
    @mouseleave="closeHint"
    @focus="openHint"
    @blur="closeHint"
  >
    <button
      ref="buttonRef"
      type="button"
      class="tt-info-hint__button"
      :aria-label="ariaLabel || title || 'Пояснение'"
    >
      <i class="pi pi-question-circle" aria-hidden="true"></i>
    </button>
  </span>
  <Teleport to="body">
    <transition name="tt-info-hint-fade">
      <div
        v-if="isOpen"
        ref="popupRef"
        class="tt-info-hint__popup"
        :style="popupStyle"
        role="tooltip"
      >
        <strong v-if="title" class="tt-info-hint__title">{{ title }}</strong>
        <p v-if="content" class="tt-info-hint__content">{{ content }}</p>
        <ul v-if="lines.length" class="tt-info-hint__list">
          <li v-for="(line, idx) in lines" :key="idx">{{ line }}</li>
        </ul>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import { defineProps, nextTick, onBeforeUnmount, ref } from 'vue';

const props = defineProps({
  title: {
    type: String,
    default: '',
  },
  content: {
    type: String,
    default: '',
  },
  lines: {
    type: Array,
    default: () => [],
  },
  ariaLabel: {
    type: String,
    default: '',
  },
  placement: {
    type: String,
    default: 'top-right',
  },
});

const isOpen = ref(false);
const triggerRef = ref(null);
const buttonRef = ref(null);
const popupRef = ref(null);
const popupStyle = ref({});

const VIEWPORT_MARGIN = 12;
const POPUP_GAP = 10;

const resolveHorizontalMode = (triggerRect, popupWidth) => {
  const centerX = triggerRect.left + triggerRect.width / 2;
  if (props.placement === 'top-left') return 'left';
  if (props.placement === 'top-center') return 'center';
  if (props.placement === 'top-right') return 'right';
  if (centerX <= window.innerWidth * 0.33) return 'left';
  if (centerX >= window.innerWidth * 0.67) return 'right';
  if (popupWidth >= window.innerWidth * 0.72) return 'left';
  return 'center';
};

const updatePosition = () => {
  if (!isOpen.value || !buttonRef.value || !popupRef.value) return;
  const triggerRect = buttonRef.value.getBoundingClientRect();
  const popupRect = popupRef.value.getBoundingClientRect();
  const horizontalMode = resolveHorizontalMode(triggerRect, popupRect.width);

  let left = triggerRect.left;
  if (horizontalMode === 'center') {
    left = triggerRect.left + triggerRect.width / 2 - popupRect.width / 2;
  } else if (horizontalMode === 'right') {
    left = triggerRect.right - popupRect.width;
  }

  left = Math.max(VIEWPORT_MARGIN, Math.min(left, window.innerWidth - popupRect.width - VIEWPORT_MARGIN));

  let top = triggerRect.top - popupRect.height - POPUP_GAP;
  if (top < VIEWPORT_MARGIN) {
    top = triggerRect.bottom + POPUP_GAP;
  }
  top = Math.max(VIEWPORT_MARGIN, Math.min(top, window.innerHeight - popupRect.height - VIEWPORT_MARGIN));

  popupStyle.value = {
    left: `${Math.round(left)}px`,
    top: `${Math.round(top)}px`,
  };
};

const handleViewportChange = () => {
  updatePosition();
};

const addViewportListeners = () => {
  window.addEventListener('resize', handleViewportChange);
  window.addEventListener('scroll', handleViewportChange, true);
};

const removeViewportListeners = () => {
  window.removeEventListener('resize', handleViewportChange);
  window.removeEventListener('scroll', handleViewportChange, true);
};

const openHint = async () => {
  isOpen.value = true;
  await nextTick();
  updatePosition();
  addViewportListeners();
};

const closeHint = () => {
  isOpen.value = false;
  removeViewportListeners();
};

onBeforeUnmount(() => {
  removeViewportListeners();
});
</script>

<style scoped>
.tt-info-hint {
  position: relative;
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
}

.tt-info-hint__button {
  width: 1.5rem;
  height: 1.5rem;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: color 0.2s ease, background 0.2s ease;
}

.tt-info-hint__button:hover,
.tt-info-hint__button:focus-visible {
  color: #0f766e;
  background: rgba(20, 184, 166, 0.12);
  outline: none;
}

.tt-info-hint__popup {
  position: fixed;
  width: min(24rem, 78vw);
  padding: 0.8rem 0.9rem;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: rgba(15, 23, 42, 0.98);
  color: #e2e8f0;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.22);
  z-index: 4000;
  pointer-events: none;
}

.tt-info-hint__title {
  display: block;
  margin-bottom: 0.4rem;
  font-size: 0.9rem;
  color: #f8fafc;
}

.tt-info-hint__content {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.5;
  color: #cbd5e1;
}

.tt-info-hint__list {
  margin: 0.4rem 0 0;
  padding-left: 1rem;
  font-size: 0.8rem;
  line-height: 1.45;
  color: #cbd5e1;
}

.tt-info-hint-fade-enter-active,
.tt-info-hint-fade-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.tt-info-hint-fade-enter-from,
.tt-info-hint-fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

@media (max-width: 640px) {
  .tt-info-hint__popup {
    width: min(20rem, 84vw);
  }
}
</style>
