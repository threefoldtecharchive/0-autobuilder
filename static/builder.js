var window_focus = true;
var was_building = false;
var artifactshost = 'https://bootstrap.gig.tech/kernel/'; // retro-compatible
var artifactshosts = {
    'kernel': 'https://bootstrap.gig.tech/kernel/',
    'flist': 'https://hub.gig.tech/gig-autobuilder/',
    'binary': 'https://download.gig.tech/gig-autobuilder/',
};
var timeouts = [];

var statuscolors = {
    'creating': 'info',
    'error': 'danger',
    'success': 'success',
    'building': 'info',
    'committing': 'info',
    'preparing': 'info',
    'initializing': 'info',
};

var statusmsg = {
    'creating': 'preparing container',
    'error': 'build failed',
    'success': 'build succeeded',
    'building': 'building',
    'committing': 'committing image',
    'preparing': 'preparing the build',
    'initializing': 'initializing the image',
};

function set_timeout(callback, time) {
    timeouts.push(setTimeout(callback, time));
}

function clear_timeouts() {
    for(var i = 0; i < timeouts.length; i++) {
        clearTimeout(timeouts[i]);
    }
}

function refresh_status(data) {
    refresh(data, 'status');
}

function refresh_history(data) {
    refresh(data, 'history');
}

function force_update() {
    clear_timeouts();
    update();
}

function refresh(data, type) {
    // console.log(data);

    $("#build-" + type).empty();

    if(type == 'status') {
        if(Object.keys(data).length == 0) {
            var text = $('<h2>', {'class': 'text-success'});
            text.append($('<span>', {'class': 'glyphicon glyphicon-ok'}));
            text.append('<br>');
            text.append('Nothing do to right now, all build done.');

            $("#build-" + type).append(text);

            // build just finished, update history
            if(was_building)
                update_history();

            set_timeout(update_status, 2 * 60 * 1000);
            return;
        }

        // update 2 seconds
        set_timeout(update_status, 2 * 1000);
        was_building = true;
    }

    if(type == 'history') {
        if(Object.keys(data).length == 0) {
            var text = $('<h2>', {'class': 'text-success'});
            text.append($('<span>', {'class': 'glyphicon glyphicon-ok'}));
            text.append('<br>');
            text.append('No history right now.');

            $("#build-" + type).append(text);
            set_timeout(update_history, 2 * 60 * 1000);
            return;
        }

        set_timeout(update_status, 30 * 1000);
    }

    var zindex = 0;
    for(var idx in data) {
        zindex++;

        var rootcommit = "";

        if(data[idx]['commits'].length > 0) {
            rootcommit = data[idx]['commits'][0]['id'].substr(0, 10);

        } else if(data[idx]['docker'] == 'system') {
            rootcommit = 'internal';

        } else rootcommit = 'docker-' + data[idx]['docker'];

        var root = $('<div>', {'class': 'panel panel-' + statuscolors[data[idx]['status']]});
        var heading = $('<div>', {'class': 'panel-heading'});

        //
        // heading
        //
        var title = data[idx]['name'];
        title = ' <code>[' + rootcommit + ']</code> ' + title;

        if(data[idx]['tag']) {
            title = title + ' [' + data[idx]['tag'] + ']';
        }

        // collapsed heading for history
        if(type == 'history') {
            var id = "panel-" + zindex + "-" + rootcommit
            var collapse = {
                'role': "button",
                'data-toggle': "collapse",
                'href': "#" + id,
                'aria-expanded': "false",
                'aria-controls': id,
            };

            var name = data[idx]['name'];
            if(data[idx]['tag']) {
                name = name + ' [' + data[idx]['tag'] + ']';
            }

            var lnk = $('<a>', collapse).html(name);
            var code = $('<code>').html('[' + rootcommit + ']');

            var title = $('<div>').append(code).append(' ').append(lnk).html();
        }

        var when = new Date(data[idx]['started'] * 1000);
        heading.append($('<h3>', {'class': 'panel-title pull-left'}).html(title));
        heading.append($('<small>', {'class': 'pull-right'}).html(when));
        heading.append($('<div>', {'class': 'clearfix'}));
        root.append(heading);

        //
        // body
        //
        var id = (type == 'history') ? "panel-" + zindex + "-" + rootcommit : "";
        var clss = (type == 'history') ? "panel-body collapse" : "panel-body";

        var content = $('<div>', {'class': clss, 'id': id});

        var text = $('<p>').html('<strong>Status</strong>: ' + statusmsg[data[idx]['status']]);
        content.append(text);

        var text = $('<p>').html('<strong>Commits</strong>:');
        content.append(text);

        var list = $('<ul>');
        for(var i in data[idx]['commits']) {
            var commit = data[idx]['commits'][i];
            var commitid = commit['id'].substr(0, 10);

            var item = $('<li>').html(
                '<code><a href="' + commit['url'] + '" target="_blank">' + commitid + '</a></code> ' +
                '<code>' + commit['message'] + '</code>' +
                '<small class="pull-right">' + commit['author']['name'] + '</small>'
            );

            list.append(item);
        }

        content.append(list);

        if(data[idx]['status'] == 'error') {
            var text = $('<p>').html('<strong>Error</strong>: ' + data[idx]['error'])
            content.append(text);
        }

        if(data[idx]['artifact']) {
            var artifact = data[idx]['artifact'];
            var segments = artifact.split("/");

            if(artifactshosts[segments[0]]) {
                var targetlink = artifactshosts[segments[0]] + segments[1];
                var artifactname = segments[1];

            } else {
                // fallback old behavior
                var targetlink = artifactshost + artifact;
                var artifactname = artifact;
            }

            var lnk = $('<a>', {'href': targetlink}).html(artifactname);
            var text = $('<p>').html('<strong>Artifact</strong>: ');
            text.append($('<code>').append(lnk));

            content.append(text);
        }

        // compute execution time
        if(data[idx]['ended']) {
            var elapsed = ((data[idx]['ended'] - data[idx]['started']) / 60).toFixed(1);
            var text = $('<p>').html('<strong>Build time</strong>: ' + elapsed + ' minutes');
            content.append(text);

        } else {
            var elapsed = (((Date.now() / 1000) - data[idx]['started']) / 60).toFixed(1);
            var text = $('<p>').html('<strong>Build started</strong>: ' + elapsed + ' minutes ago');
            content.append(text);
        }

        // do not shot console if empty
        if(data[idx]['monitor']) {
            var logs = $('<pre>').html(data[idx]['monitor']);

            content.append($('<hr>'));
            content.append(logs);
        }

        // probably a build id, not a numeric id
        if(idx.length > 10) {
            data[idx]['id'] = idx;
        }

        if(data[idx]['id']) {
            var options = {
                'href': '/report/' + data[idx]['id'],
                'target': '_blank',
                'style': 'float: right;',
            };

            var report = $('<a>', options).html('View full logs');
            content.append(report);
        }

        root.append(content);

        $("#build-" + type).append(root);
    }
}

function update_status() {
    if(!window_focus)
        return;

    $.get('/build/status', refresh_status);
}

function update_history() {
    if(!window_focus)
        return;

    $.get('/build/history', refresh_history);
}

function update() {
    update_status();
    update_history();
}

$(document).ready(function() {
    update();
});

$(window).focus(function() {
    if(!window_focus) {
        window_focus = true;
        update();
    }

    window_focus = true;

}).blur(function() {
    window_focus = false;
});
