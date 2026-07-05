const form = document.querySelector("#upload-form");
const preview = document.querySelector("#preview");
const result = document.querySelector("#result");
const errorSummary = document.querySelector("#error-summary");
const previewRows = document.querySelector("#preview-rows");
const confirmButton = document.querySelector("#confirm-button");
const backButton = document.querySelector("#back-button");
const downloadLink = document.querySelector("#download-link");

let activeJobId = null;

function listFiles(panel) {
  const input = panel.querySelector('input[type="file"]');
  const list = panel.querySelector(".file-list");
  list.replaceChildren();
  [...input.files].forEach((file, index) => {
    const item = document.createElement("li");
    item.append(document.createTextNode(file.name));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-file ghost";
    remove.textContent = "删除";
    remove.addEventListener("click", () => removeFile(input, index));
    item.append(remove);
    list.append(item);
  });
}

async function invalidatePreview() {
  if (activeJobId) {
    await fetch(`/api/jobs/${activeJobId}`, { method: "DELETE" });
  }
  activeJobId = null;
  preview.hidden = true;
  previewRows.replaceChildren();
}

async function removeFile(input, removedIndex) {
  const transfer = new DataTransfer();
  [...input.files].forEach((file, index) => {
    if (index !== removedIndex) {
      transfer.items.add(file);
    }
  });
  input.files = transfer.files;
  listFiles(input.closest(".group-panel"));
  await invalidatePreview();
}

function clearErrors() {
  errorSummary.hidden = true;
  errorSummary.replaceChildren();
  document.querySelectorAll(".group-error").forEach((element) => {
    element.hidden = true;
    element.replaceChildren();
  });
}

function formatIssue(issue) {
  const parts = [issue.message];
  if (issue.expected !== undefined || issue.actual !== undefined) {
    parts.push(`期望：${issue.expected ?? "-"}`);
    parts.push(`实际：${issue.actual ?? "-"}`);
  }
  parts.push(issue.repair);
  return parts.join("。");
}

function showIssues(issues) {
  clearErrors();
  errorSummary.hidden = false;
  errorSummary.textContent = "校验未通过，请按组修正以下问题。";
  issues.forEach((issue) => {
    const target = issue.group_index
      ? document.querySelector(`[data-group="${issue.group_index}"] .group-error`)
      : errorSummary;
    target.hidden = false;
    const line = document.createElement("p");
    line.textContent = formatIssue(issue);
    target.append(line);
  });
}

function clearPanelFiles(panel) {
  const input = panel.querySelector('input[type="file"]');
  input.value = "";
  listFiles(panel);
  panel.querySelector(".group-error").hidden = true;
}

async function discardAndClearAll() {
  await invalidatePreview();
  document.querySelectorAll(".group-panel").forEach(clearPanelFiles);
  form.reset();
  preview.hidden = true;
  result.hidden = true;
  previewRows.replaceChildren();
  clearErrors();
}

function resetInputsAfterSuccess() {
  document.querySelectorAll(".group-panel").forEach(clearPanelFiles);
  form.reset();
  activeJobId = null;
  preview.hidden = true;
  previewRows.replaceChildren();
  clearErrors();
}

document.querySelectorAll('.group-panel input[type="file"]').forEach((input) => {
  input.addEventListener("change", () => {
    listFiles(input.closest(".group-panel"));
    invalidatePreview();
  });
});

document.querySelectorAll(".clear-group").forEach((button) => {
  button.addEventListener("click", async () => {
    await invalidatePreview();
    clearPanelFiles(button.closest(".group-panel"));
  });
});

document.querySelector("#clear-all").addEventListener("click", discardAndClearAll);

backButton.addEventListener("click", () => {
  preview.hidden = true;
  form.hidden = false;
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await invalidatePreview();
  clearErrors();
  const response = await fetch("/api/jobs/validate", {
    method: "POST",
    body: new FormData(form),
  });
  const body = await response.json();
  if (!response.ok) {
    showIssues(body.detail?.issues ?? []);
    return;
  }

  activeJobId = body.job_id;
  previewRows.replaceChildren(
    ...body.preview.pairs.map((pair) => {
      const row = document.createElement("tr");
      [
        pair.group_index,
        pair.box_index,
        pair.wfs_pdf_page,
        pair.sku,
        pair.logistics_pdf_page,
        pair.output_sequence.join(" "),
      ].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      return row;
    }),
  );
  form.hidden = true;
  result.hidden = true;
  preview.hidden = false;
});

confirmButton.addEventListener("click", async () => {
  const response = await fetch(`/api/jobs/${activeJobId}/generate`, { method: "POST" });
  const body = await response.json();
  if (!response.ok) {
    showIssues(body.detail?.issues ?? []);
    form.hidden = false;
    preview.hidden = true;
    return;
  }

  const url = body.download_url;
  resetInputsAfterSuccess();
  form.hidden = false;
  result.hidden = false;
  downloadLink.href = url;
});
