(function() {
  'use strict';

  // Inject CSS with ts- prefix
  var style = document.createElement('style');
  style.textContent = [
    '.ts-strip {',
    '  position: fixed;',
    '  top: 58px;',  // below the star page's own top row (#top-right ends at 50px), so neither covers the other
    '  left: 50%;',
    '  transform: translateX(-50%);',
    '  height: 32px;',
    '  max-width: 720px;',
    '  width: max-content;',
    '  background: rgba(10, 14, 24, 0.72);',
    '  border-radius: 16px;',
    '  color: #ffffff;',
    '  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;',
    '  font-size: 13px;',
    '  line-height: 1;',
    '  opacity: 0.55;',
    '  transition: opacity 0.2s ease;',
    '  z-index: 999999;',
    '  display: flex;',
    '  align-items: center;',
    '  padding: 0 12px;',
    '  box-sizing: border-box;',
    '  pointer-events: auto;',
    '  user-select: none;',
    '  white-space: nowrap;',
    '}',
    '.ts-strip:hover {',
    '  opacity: 1;',
    '}',
    '.ts-label {',
    '  font-weight: 600;',
    '  color: #ffffff;',
    '  margin-right: 8px;',
    '  flex-shrink: 0;',
    '  font-size: 13px;',
    '}',
    '.ts-blocks {',
    '  display: flex;',
    '  align-items: center;',
    '  gap: 6px;',
    '  overflow: hidden;',
    '}',
    '.ts-block {',
    '  display: inline-flex;',
    '  align-items: center;',
    '  background: rgba(255, 255, 255, 0.1);',
    '  border-radius: 10px;',
    '  padding: 2px 8px;',
    '  gap: 4px;',
    '  max-width: 180px;',
    '  flex-shrink: 0;',
    '  box-sizing: border-box;',
    '  line-height: 1.2;',
    '}',
    '.ts-tag {',
    '  font-size: 10px;',
    '  padding: 1px 4px;',
    '  border-radius: 3px;',
    '  flex-shrink: 0;',
    '}',
    '.ts-tag-overdue {',
    '  background: #F2A33A;',
    '  color: #000000;',
    '  font-weight: 600;',
    '}',
    '.ts-tag-gray {',
    '  background: rgba(255, 255, 255, 0.2);',
    '  color: #e5e5e5;',
    '}',
    '.ts-title {',
    '  font-size: 12px;',
    '  color: #ffffff;',
    '  overflow: hidden;',
    '  text-overflow: ellipsis;',
    '  white-space: nowrap;',
    '}',
    '.ts-more {',
    '  font-size: 12px;',
    '  color: rgba(255, 255, 255, 0.7);',
    '  margin-left: 6px;',
    '  flex-shrink: 0;',
    '}',
    '.ts-notice {',
    '  font-size: 12px;',
    '  color: rgba(255, 255, 255, 0.7);',
    '}'
  ].join('\n');

  if (document.head) {
    document.head.appendChild(style);
  } else {
    document.documentElement.appendChild(style);
  }

  // Create strip element
  var strip = document.createElement('div');
  strip.className = 'ts-strip';

  function attachStrip() {
    if (document.body) {
      if (!strip.parentNode) {
        document.body.appendChild(strip);
      }
    } else {
      document.addEventListener('DOMContentLoaded', function() {
        if (!strip.parentNode && document.body) {
          document.body.appendChild(strip);
        }
      });
    }
  }
  attachStrip();

  var currentRev = null;
  var hasRenderedData = false;

  function renderData(data) {
    strip.innerHTML = '';

    // "今天" label
    var label = document.createElement('span');
    label.className = 'ts-label';
    label.textContent = '今天';
    strip.appendChild(label);

    var blocksContainer = document.createElement('div');
    blocksContainer.className = 'ts-blocks';

    var visibleCount = (typeof data.visible === 'number') ? data.visible : 4;
    var rawItems = data.items || [];
    var visibleItems = rawItems.slice(0, visibleCount);

    visibleItems.forEach(function(itemObj) {
      var block = document.createElement('div');
      block.className = 'ts-block';
      block.setAttribute('data-id', itemObj.id || '');
      block.setAttribute('title', itemObj.next || '');

      if (itemObj.item) {
        block.style.cursor = 'pointer';
      } else {
        block.style.cursor = 'default';
      }

      // Small tag
      var tagSpan = document.createElement('span');
      tagSpan.className = 'ts-tag ' + (itemObj.tag === '逾期' ? 'ts-tag-overdue' : 'ts-tag-gray');
      tagSpan.textContent = itemObj.tag || '';
      block.appendChild(tagSpan);

      // Title (truncate > 10 chars + '…')
      var titleSpan = document.createElement('span');
      titleSpan.className = 'ts-title';
      var titleText = itemObj.title || '';
      if (titleText.length > 10) {
        titleText = titleText.slice(0, 10) + '…';
      }
      titleSpan.textContent = titleText;
      block.appendChild(titleSpan);

      // Click handler
      block.addEventListener('click', function(e) {
        e.stopPropagation();
        if (!itemObj.item) return;
        var item = itemObj.item;
        var n = (typeof getNode === 'function') ? getNode('item:' + item) : null;
        if (n && typeof flyToNode === 'function') flyToNode(n);
      });

      blocksContainer.appendChild(block);
    });

    strip.appendChild(blocksContainer);

    // "+N" when more > 0
    if (data.more && data.more > 0) {
      var moreSpan = document.createElement('span');
      moreSpan.className = 'ts-more';
      moreSpan.textContent = '+' + data.more;
      strip.appendChild(moreSpan);
    }

    hasRenderedData = true;
  }

  function fetchUnified() {
    fetch('/api/today-unified')
      .then(function(res) {
        if (!res.ok) throw new Error('Fetch failed');
        return res.json();
      })
      .then(function(data) {
        if (hasRenderedData && currentRev && data.rev === currentRev) {
          return; // Skip re-rendering if rev unchanged
        }
        currentRev = data.rev;
        renderData(data);
      })
      .catch(function() {
        if (!hasRenderedData) {
          strip.innerHTML = '<span class="ts-label">今天</span><span class="ts-notice">接口没连上</span>';
        }
      });
  }

  fetchUnified();
  setInterval(fetchUnified, 5000);

})();
