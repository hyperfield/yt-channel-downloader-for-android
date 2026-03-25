package com.ytchanneldownloader.android

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.CheckBox
import android.widget.ImageView
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.ytchanneldownloader.android.bridge.ResolvedItem

class ResolvedItemsAdapter(
    private val onSelectionChanged: (itemUrl: String, selected: Boolean) -> Unit,
) : RecyclerView.Adapter<ResolvedItemsAdapter.ItemViewHolder>() {
    private var items: List<ResolvedItem> = emptyList()
    private var selectedUrls: Set<String> = emptySet()
    private var showThumbnails: Boolean = true

    fun submit(
        items: List<ResolvedItem>,
        selectedUrls: Set<String>,
        showThumbnails: Boolean,
    ) {
        this.items = items
        this.selectedUrls = selectedUrls
        this.showThumbnails = showThumbnails
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ItemViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_resolved_media, parent, false)
        return ItemViewHolder(view as ViewGroup)
    }

    override fun onBindViewHolder(holder: ItemViewHolder, position: Int) {
        val item = items[position]
        val title = if (item.title.isBlank()) item.url else item.title
        val label = "${position + 1}. $title"
        holder.bind(
            label = label,
            selected = selectedUrls.contains(item.url),
            thumbnailUrl = item.thumbnailUrl,
            showThumbnail = showThumbnails,
        ) { selected ->
            onSelectionChanged(item.url, selected)
        }
    }

    override fun getItemCount(): Int = items.size

    class ItemViewHolder(
        container: ViewGroup,
    ) : RecyclerView.ViewHolder(container) {
        private val checkBox: CheckBox = container.findViewById(R.id.itemCheckBox)
        private val thumbnailView: ImageView = container.findViewById(R.id.itemThumbnailView)
        private val titleView: TextView = container.findViewById(R.id.itemTitleView)

        fun bind(
            label: String,
            selected: Boolean,
            thumbnailUrl: String?,
            showThumbnail: Boolean,
            onSelectionChanged: (selected: Boolean) -> Unit,
        ) {
            titleView.text = label
            checkBox.isChecked = selected
            if (showThumbnail) {
                thumbnailView.visibility = View.VISIBLE
                ThumbnailImageLoader.loadInto(thumbnailView, thumbnailUrl)
            } else {
                thumbnailView.visibility = View.GONE
                thumbnailView.setImageDrawable(null)
            }
            itemView.setOnClickListener {
                onSelectionChanged(!checkBox.isChecked)
            }
        }
    }
}
