/**
 * static/js/upload.js
 * --------------------
 * Handles the presigned-URL upload flow entirely client-side:
 *   1. Ask Flask for a presigned PUT URL (+ image_id) for each file.
 *   2. PUT the file bytes directly to S3.
 *   3. Poll Flask for processing status until it's "done" or "failed".
 *
 * No page reload is required to see results, though a manual refresh
 * will also show the finished state via the server-rendered gallery.
 */
(function () {
    const projectId = window.PIXELFORGE_PROJECT_ID;
    if (!projectId) return;

    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("file-input");
    const uploadList = document.getElementById("upload-list");

    if (dropzone && fileInput) {
        dropzone.addEventListener("click", () => fileInput.click());

        dropzone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropzone.classList.add("dragover");
        });
        dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
        dropzone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropzone.classList.remove("dragover");
            handleFiles(e.dataTransfer.files);
        });

        fileInput.addEventListener("change", () => {
            handleFiles(fileInput.files);
            fileInput.value = "";
        });
    }

    function handleFiles(fileList) {
        Array.from(fileList).forEach(uploadOneFile);
    }

    async function uploadOneFile(file) {
        const row = createUploadRow(file.name);

        try {
            const presignResp = await fetch(`/projects/${projectId}/images/presign`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    filename: file.name,
                    content_type: file.type,
                    size_bytes: file.size,
                }),
            });

            if (!presignResp.ok) {
                const err = await presignResp.json().catch(() => ({}));
                throw new Error(err.error || "Could not start upload.");
            }

            const { image_id, upload_url } = await presignResp.json();
            updateUploadRow(row, "Uploading...");

            const putResp = await fetch(upload_url, {
                method: "PUT",
                headers: { "Content-Type": file.type },
                body: file,
            });

            if (!putResp.ok) {
                throw new Error("Upload to storage failed.");
            }

            updateUploadRow(row, "Processing...");
            pollStatus(image_id, row);
        } catch (err) {
            updateUploadRow(row, `Failed: ${err.message}`, true);
        }
    }

    function pollStatus(imageId, row) {
        const intervalMs = 2500;
        const maxAttempts = 40; // ~100 seconds
        let attempts = 0;

        const timer = setInterval(async () => {
            attempts += 1;
            try {
                const resp = await fetch(`/projects/${projectId}/images/${imageId}/status`);
                const data = await resp.json();

                if (data.status === "done") {
                    clearInterval(timer);
                    updateUploadRow(row, "Done \u2014 refresh to view variants.");
                    setTimeout(() => window.location.reload(), 1200);
                } else if (data.status === "failed") {
                    clearInterval(timer);
                    updateUploadRow(row, `Failed: ${data.error_message || "processing error"}`, true);
                } else if (attempts >= maxAttempts) {
                    clearInterval(timer);
                    updateUploadRow(row, "Still processing \u2014 check back shortly.");
                }
            } catch (err) {
                // Transient network errors during polling are not fatal; keep trying.
                if (attempts >= maxAttempts) {
                    clearInterval(timer);
                    updateUploadRow(row, "Could not confirm processing status.", true);
                }
            }
        }, intervalMs);
    }

    function createUploadRow(filename) {
        const row = document.createElement("div");
        row.className = "upload-item";
        row.innerHTML = `<span>${escapeHtml(filename)}</span><span class="upload-status">Starting...</span>`;
        uploadList.prepend(row);
        return row;
    }

    function updateUploadRow(row, text, isError) {
        const statusEl = row.querySelector(".upload-status");
        statusEl.textContent = text;
        statusEl.style.color = isError ? "#ff6b6b" : "#8b92a3";
    }

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // Delete buttons in the image gallery
    document.querySelectorAll(".delete-image-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
            if (!confirm("Delete this image and its variants?")) return;
            const imageId = btn.dataset.imageId;
            const card = btn.closest(".image-card");
            btn.disabled = true;
            try {
                const resp = await fetch(`/projects/${projectId}/images/${imageId}/delete`, { method: "POST" });
                if (resp.ok) {
                    card.remove();
                } else {
                    alert("Could not delete image.");
                    btn.disabled = false;
                }
            } catch (err) {
                alert("Network error while deleting image.");
                btn.disabled = false;
            }
        });
    });
})();
