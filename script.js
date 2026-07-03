function switchTab(tabId) {
    // Hide all tab contents
    const contents = document.querySelectorAll('.tab-content');
    contents.forEach(content => content.style.display = 'none');

    // Remove active class from all buttons
    const buttons = document.querySelectorAll('.tab-btn');
    buttons.forEach(btn => btn.classList.remove('active'));

    // Show the selected tab
    document.getElementById('tab-' + tabId).style.display = 'block';

    // Highlight active button
    event.currentTarget.classList.add('active');
}