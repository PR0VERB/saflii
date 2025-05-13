document.addEventListener('DOMContentLoaded', function () {
    // Find all project item lists (one per query group)
    const itemLists = document.querySelectorAll('.project-item-list');

    itemLists.forEach(listElement => {
        // Only make sortable if there's more than one item to drag
        if (listElement.children.length > 1) {
            new Sortable(listElement, {
                animation: 150, // ms, animation speed moving items when sorting, `0` — without animation
                ghostClass: 'sortable-ghost', // Class name for the drop placeholder
                chosenClass: 'sortable-chosen', // Class name for the chosen item
                dragClass: 'sortable-drag', // Class name for the dragging item
                handle: '.drag-handle', // Specify the drag handle element

                // Element dragging ended
                onEnd: function (/**Event*/evt) {
                    const itemContainer = evt.to; // The container element where the drop happened
                    const items = itemContainer.children;
                    const orderedItemIds = [];

                    for (let i = 0; i < items.length; i++) {
                        // Extract the full UUID from 'project-item-xxxxxxxx-xxxx...'
                        const elementId = items[i].id;
                        const prefix = 'project-item-';
                        if (elementId.startsWith(prefix)) {
                            const itemId = elementId.substring(prefix.length);
                            orderedItemIds.push(itemId);
                        } else {
                            console.warn(`Could not extract UUID from element ID: ${elementId}`);
                        }
                    }

                    // Send the new order to the backend
                    if (orderedItemIds.length > 0) {
                        fetch('/api/project_items/reorder', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                // If you implement CSRF protection (recommended), add the token header here
                                // 'X-CSRFToken': getCsrfToken() // Assuming a function getCsrfToken exists
                            },
                            body: JSON.stringify({
                                ordered_ids: orderedItemIds
                                // If your endpoint needs the project ID, you'd retrieve it here,
                                // perhaps from a data attribute on itemContainer or a parent element.
                                // project_id: itemContainer.closest('[data-project-id]').dataset.projectId
                            })
                        })
                        .then(response => {
                            if (!response.ok) {
                                // Throw an error to be caught by the .catch block
                                throw new Error(`HTTP error! status: ${response.status}`);
                            }
                            return response.json();
                        })
                        .then(data => {
                            if (data.status === 'success') {
                                console.log('Order updated successfully.');
                                // Optional: Add user feedback (e.g., toast notification)
                            } else {
                                console.error('Failed to update order:', data.message);
                                alert('Error saving new order: ' + (data.message || 'Unknown error'));
                                // Optional: Revert the order visually if the save failed
                            }
                        })
                        .catch(error => {
                            console.error('Error sending reorder request:', error);
                            alert('Error saving new order. Please check console or try again.');
                        });
                    }
                },
            });
        }
    });

    // Example function to get CSRF token if needed (adapt based on your setup)
    // function getCsrfToken() {
    //     const csrfTokenInput = document.querySelector('input[name="csrf_token"]');
    //     return csrfTokenInput ? csrfTokenInput.value : null;
    // }
});